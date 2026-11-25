"""Shadow collector for the public YouTube channel Atom feed.

This package does not score demand, does not write director_v1, and does not
treat a channel as SKU coverage.
"""

SOURCE = "youtube_official_feed_v1"
RULE_VERSION = "press_on_christmas_v1"
FEED_CAP = 15
RETENTION_DAYS = 30
USER_AGENT = (
    "dacu-signal-youtube-official-feed/1.0 "
    "(shadow research; no cookies; public Atom feed only)"
)

LICENSE_BASIS = (
    "Public GET of https://www.youtube.com/feeds/videos.xml?channel_id=ID only. "
    "Reviewed YouTube API Services Developer Policies III.E on 2026-11-25: "
    "a successful read is not a redistribution or commercial-storage license. "
    "Whether this Atom feed is YouTube API Data is uncertain. Non-authorized "
    "statistics are therefore retained at most 30 days and are not used as a "
    "score. Audiovisual files are not downloaded. No login and no API key."
)

DELTA_DISCLOSURE = (
    "observed_cohort_views_delta is this system's arithmetic difference between "
    "two stored cumulative view snapshots of one video. It is not a YouTube "
    "metric, not daily views, not sales, and not a director score. The interval "
    "is the actual retrieved_at gap. A partial flag means the gap is not an "
    "exact UTC-day boundary match."
)
