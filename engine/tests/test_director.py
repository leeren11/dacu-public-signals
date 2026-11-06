import unittest,sys,json,sqlite3,math,hashlib
from pathlib import Path
sys.path.insert(0,'/workspace/dacu-signal/scripts')
from rolling_engine import connect,apply_migrate_v4,compute_rolling_for_as_of,metric_features,persist_rolling
from director_schema import migrate,ROOT
from director_model import eligible
from backfill_actuals import ranks,spearman
class DirectorTests(unittest.TestCase):
    def setUp(self):
        src=connect();self.con=sqlite3.connect(':memory:');self.con.row_factory=sqlite3.Row;src.backup(self.con);src.close();migrate(self.con)
    def tearDown(self):self.con.close()
    def test_t0_unchanged(self):
        snap=json.loads((ROOT/'data/pre_director_t0_snapshot.json').read_text())
        for table in ('prediction_items','prediction_freeze'):
            self.assertEqual(snap[table],[dict(r) for r in self.con.execute('select * from '+table)])
        self.assertEqual(snap['freeze_sha256'],hashlib.sha256(Path('/workspace/dacu-public-signals-stamp/freeze/T0_2026-11-02_top9.md').read_bytes()).hexdigest())
    def test_five_dimensions_and_repeatability(self):
        rows,meta,*_=compute_rolling_for_as_of(self.con,'2026-11-06');persist_rolling(self.con,rows,meta)
        rows2,meta,*_=compute_rolling_for_as_of(self.con,'2026-11-06');persist_rolling(self.con,rows2,meta)
        self.assertEqual([r.live_total for r in rows],[r.live_total for r in rows2])
        self.assertEqual(9,self.con.execute("select count(*) from rolling_sku_scoring where as_of_date='2026-11-06'").fetchone()[0])
        for r in rows:
            dims=[r.multi_platform_demand,r.content_ad_leverage,r.fulfillment_sla,r.margin_return_risk,r.white_label_viability]
            self.assertTrue(all(0<=v<=5 and round(v,1)==v for v in dims));self.assertAlmostEqual(r.live_total,sum(dims)+r.catalyst_adj)
            self.assertEqual(r.rank_delta,r.t0_rank-r.rolling_rank)
    def test_temporal_filter(self):
        row=dict(sku_cluster_or_topic='*',value=100,status='context',is_partial=0,signal_date='2026-11-05',available_at='2026-11-06')
        self.assertFalse(eligible(row,'holiday press-on nails','2026-11-06'))
        row['status']='observed';self.assertTrue(eligible(row,'holiday press-on nails','2026-11-06'))
        row['is_partial']=1;self.assertFalse(eligible(row,'holiday press-on nails','2026-11-06'))
        row['is_partial']=0;row['available_at']='2026-11-07';self.assertFalse(eligible(row,'holiday press-on nails','2026-11-06'))
    def test_single_platform_noise_and_daily_resonance(self):
        sku='soft squishy multipack';original=next(r for r in compute_rolling_for_as_of(self.con,'2026-11-06')[0] if r.sku_cluster==sku)
        self.assertLess(original.multi_platform_demand,3.1)
        rid='2026-11-06_scheduled_0905'
        self.con.execute('''insert into platform_signals(run_id,signal_date,platform,channel,metric_key,sku_cluster_or_topic,value,unit,slope_7d,dod_pct,is_partial,is_proxy,source_url,source_note,as_of_ts,available_at,status) values (?,'2026-11-05','GoogleTrends','test','search_velocity',?,100,'index',8,80,0,1,'https://example.org','SYNTHETIC TEST ONLY','2026-11-06T09:00:00+08:00','2026-11-06','observed')''',(rid,sku))
        row=next(r for r in compute_rolling_for_as_of(self.con,'2026-11-06')[0] if r.sku_cluster==sku)
        self.assertGreater(row.multi_platform_demand,original.multi_platform_demand)
    def test_features_calendar_days(self):
        val,dod,slope,hot=metric_features([('2026-11-01',10),('2026-11-03',30)],'2026-11-03')
        self.assertIsNone(dod);self.assertEqual(slope,10);self.assertEqual(hot,0)
    def test_rank_ties(self):
        self.assertEqual(ranks([3,3,1]),[1.5,1.5,3])
        self.assertAlmostEqual(spearman([3,2,1],[30,20,10]),1)
        self.assertAlmostEqual(spearman([3,2,1],[10,20,30]),-1)
        self.assertIsNone(spearman([1,1,1],[1,2,3]))
    def test_migration_idempotence(self):
        migrate(self.con);migrate(self.con)
        self.assertEqual(self.con.execute("select count(*) from schema_migrations where version='5'").fetchone()[0],1)
if __name__=='__main__':unittest.main()
