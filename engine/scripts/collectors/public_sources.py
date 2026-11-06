"""Public source adapters. Raw response evidence and explicit NULLs, never estimates.
Monthly Newsroom context is NOT daily content/search velocity. Every row carries
its observation window; historical runs cannot use today's snapshot as a past fact.
"""
import hashlib,json,re,time
from datetime import date,datetime,timedelta,timezone
from pathlib import Path
from urllib.parse import urlencode,urlparse
from concurrent.futures import ThreadPoolExecutor
import requests
from bs4 import BeautifulSoup
ROOT=Path('/workspace/dacu-signal')
RAW=ROOT/'data/platform_raw'
SH=timezone(timedelta(hours=8))
NEWS='https://newsroom.tiktok.com/whats-shaping-the-holiday-season-on-tiktok-shop?lang=en'
# Dated public syndication for provenance of the older monthly release.
NEWS_PUBLICATION='2026-10-19'

def fetch(url):
    key=hashlib.sha256(url.encode()).hexdigest()[:20]
    cache=RAW/(date.today().isoformat()+'_'+key+'.json')
    if cache.exists(): return json.loads(cache.read_text())
    now=datetime.now(SH).isoformat()
    # Respect platform denial/rate-limit for the rest of the day across queries.
    # No proxy/browser/token bypass and no automatic repeat at another URL.
    for prior_path in RAW.glob(date.today().isoformat()+'_*.json'):
        prior=json.loads(prior_path.read_text())
        if urlparse(prior['url']).netloc==urlparse(url).netloc and prior.get('http_status') in (403,429):
            data={'url':url,'fetched_at':now,'http_status':prior['http_status'],'body':'','error':f"HTTP {prior['http_status']} earlier on same public host; skipped additional request, no retry or bypass"}
            cache.write_text(json.dumps(data));return data
    try:
        response=requests.get(url,timeout=18,headers={'User-Agent':'DacuPublicResearch/1.0 (public aggregate research)'})
        body=response.text
        data={'url':url,'fetched_at':now,'http_status':response.status_code,'body':body,'error':None if response.ok else f'HTTP {response.status_code}'}
    except requests.RequestException as e:
        data={'url':url,'fetched_at':now,'http_status':None,'body':'','error':str(e)}
    RAW.mkdir(parents=True,exist_ok=True);cache.write_text(json.dumps(data,ensure_ascii=False))
    return data

def observation(platform,channel,metric,topic,url,day,**kw):
    return dict(platform=platform,channel=channel,metric_key=metric,sku_cluster_or_topic=topic,source_url=url,signal_date=day,value=None,unit='unavailable',slope_7d=None,dod_pct=None,is_partial=0,is_proxy=1,status='missing',source_note='No public dated measurement.',period_start=day,period_end=day,available_at=None,**kw)

def collect(as_of,watch):
    yday=(date.fromisoformat(as_of)-timedelta(days=1)).isoformat()
    urls={
        'news':NEWS,
        'creative':'https://ads.tiktok.com/business/creativecenter/inspiration/popular/hashtag/pc/en',
        'meta':'https://www.facebook.com/ads/library/?'+urlencode({'active_status':'active','ad_type':'all','country':'US','q':'christmas gifts','search_type':'keyword_unordered'}),
        'ig':'https://www.instagram.com/explore/tags/stockingstuffers/',
        'youtube':'https://www.youtube.com/results?'+urlencode({'search_query':'shorts best gifts under 25 christmas 2026'}),
        'trends':'https://trends.google.com/trends/explore?'+urlencode({'geo':'US','q':','.join(watch['search_terms']),'date':f'{(date.fromisoformat(yday)-timedelta(days=6)).isoformat()} {yday}'}),
    }
    for sub in watch['subreddits']:
        urls['reddit_'+sub]=f'https://www.reddit.com/r/{sub}/new.json?limit=100'
    with ThreadPoolExecutor(max_workers=5) as pool:
        results=dict(zip(urls,pool.map(fetch,urls.values())))
    out=[]
    specs=[('TikTok','CreativeCenter','content_velocity','creative'),('TikTok','CreativeCenter','engagement_rate','creative'),('Meta','AdLibrary','active_ads','meta'),('Meta','Instagram','reels_keyword_velocity','ig'),('YouTube','public_search','video_view_velocity','youtube'),('GoogleTrends','explore','search_velocity','trends')]
    for platform,channel,metric,key in specs:
        data=results[key]
        for sku,profile in watch['profiles'].items():
            row=observation(platform,channel,metric,sku,urls[key],yday)
            row['source_note']=(data['error'] or 'HTTP 200 but no documented, dated public aggregate series in static response; dynamic/login interface is not an observed count.')+' Historical recovery: unavailable; no backdated current snapshots.'
            row['as_of_ts']=data['fetched_at'];out.append(row)
    # Extract only source-asserted monthly percentages; never encode as DoD/slope.
    data=results['news'];text=BeautifulSoup(data['body'],'html.parser').get_text(' ',strip=True)
    context=[('matching family Christmas PJs flannel','christmaspajamas',297),('holiday press-on nails','fall nails',333),('soft squishy multipack','squishy toys',149),('gold medium/chunky hoop earrings','gold jewelry',1134),('opal/birthstone/initial pendant (ready-stock)','opal rings',825),('friendship/beaded charm bracelet','friendshipbracelet',120)]
    for sku,term,expected in context:
        row=observation('TikTok','Newsroom','reported_monthly_growth',sku,NEWS,'2026-09-30')
        row.update(period_start='2026-08-01',period_end='2026-09-30',available_at=NEWS_PUBLICATION,as_of_ts=data['fetched_at'],unit='percent_month_over_month')
        # Exact term followed by expected published number within a short span.
        match=re.search(re.escape(term)+r'.{0,130}?'+re.escape(f'{expected:,}')+r'%',text,re.I)
        if not data['error'] and match and as_of>=NEWS_PUBLICATION:
            row.update(value=float(expected),status='context',source_note=f'Official reported August→September 2026 monthly growth for {term}; not November growth, not daily DoD, not 7d slope. Dated release syndicated 2026-10-19. Raw response retained. Context excluded from daily resonance.')
        else: row['source_note']=data['error'] or f'Could not verify literal {term} / {expected}% in fetched public page.'
        out.append(row)
    # Explicit coverage gaps for requested generic hashtag daily series.
    for tag in watch['hashtags']:
        row=observation('TikTok','CreativeCenter','hashtag_daily_growth',tag,urls['creative'],yday)
        row.update(as_of_ts=results['creative']['fetched_at'],source_note=results['creative']['error'] or 'No timestamped daily hashtag series in public static response; NULL, not Newsroom monthly substitution.')
        out.append(row)
    # YouTube public search HTML has rendered video view counts. These are a
    # sampled point-in-time snapshot, NEVER a full daily platform volume or an
    # invented historical slope. Historical rerenders cannot borrow today's views.
    yt=results['youtube']
    videos=[]
    if not yt['error']:
        marker=re.search(r'(?:var )?ytInitialData\s*=\s*',yt['body'])
        if marker:
            try:
                payload,_=json.JSONDecoder().raw_decode(yt['body'][marker.end():])
                def visit(node):
                    if isinstance(node,dict):
                        if 'videoRenderer' in node:videos.append(node['videoRenderer'])
                        for value in node.values():visit(value)
                    elif isinstance(node,list):
                        for value in node:visit(value)
                visit(payload)
            except (ValueError,TypeError):pass
    def txt(node):
        return node.get('simpleText','') or ''.join(x.get('text','') for x in node.get('runs',[]))
    def view_count(text):
        match=re.fullmatch(r'([\d,.]+)\s*([KMB])? views?',text,re.I)
        if not match:return None
        return float(match[1].replace(',',''))*{'K':1000,'M':1000000,'B':1000000000,None:1}[match[2].upper() if match[2] else None]
    if as_of==date.today().isoformat():
        for sku,profile in watch['profiles'].items():
            tokens=[t for t in re.findall('[a-z]+',profile['query'].lower()) if len(t)>3 and t not in ('gifts','christmas','family','holiday','ready','stock')]
            relevant=[v for v in videos if any(t in txt(v.get('title',{})).lower() for t in tokens)]
            counts=[view_count(txt(v.get('viewCountText',{}))) for v in relevant]
            counts=[v for v in counts if v is not None]
            if counts:
                row=observation('YouTube','public_search','sampled_video_views_snapshot',sku,urls['youtube'],as_of)
                row.update(value=sum(counts),unit='sampled_lifetime_video_views',is_partial=1,status='snapshot',as_of_ts=yt['fetched_at'],available_at=as_of,source_note=f'Public search sample n={len(counts)}, title-keyword matched; lifetime displayed view totals at fetch time, selection-biased, not Shorts-specific, not daily volume, excluded from complete-day scoring. Never backdated.')
                out.append(row)
    # Public subreddit sample: valid if the sample covers the entire requested UTC day.
    for sub in watch['subreddits']:
        data=results['reddit_'+sub];posts=[]
        if not data['error']:
            try: posts=[p['data'] for p in json.loads(data['body'])['data']['children']]
            except (ValueError,KeyError,TypeError): pass
        start=datetime.fromisoformat(yday).replace(tzinfo=timezone.utc).timestamp();end=start+86400
        coverage=bool(posts) and min(p.get('created_utc',end) for p in posts)<=start
        for sku,profile in watch['profiles'].items():
            row=observation('Reddit',sub,'complaint_share',sku,urls['reddit_'+sub],yday)
            row.update(as_of_ts=data['fetched_at'],unit='fraction')
            if coverage:
                tokens=[t for t in re.findall('[a-z]+',profile['query'].lower()) if len(t)>3]
                selected=[p for p in posts if start<=p.get('created_utc',0)<end and any(t in (p.get('title','')+' '+p.get('selftext','')).lower() for t in tokens)]
                if selected:
                    negative=sum(any(k in (p.get('title','')+' '+p.get('selftext','')).lower() for k in watch['risk_keywords']) for p in selected)
                    row.update(value=negative/len(selected),status='observed',available_at=as_of,source_note=f'Public new-listing sample covers UTC day; keyword-matched n={len(selected)}, complaint-keyword n={negative}. Lexical proxy, not return rate; sample-selection bias.')
            if row['value'] is None: row['source_note']=data['error'] or 'Public listing cannot fully cover target historical UTC day or no relevant sample; NULL, never zero sentiment.'
            out.append(row)
    for row in out:
        row.setdefault('as_of_ts',datetime.now(SH).isoformat())
    return out
