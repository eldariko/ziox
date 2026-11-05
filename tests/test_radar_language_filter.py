"""Unit tests for early language filtering in DiscoveryRadar."""

from datetime import datetime, timezone
from unittest.mock import MagicMock
from engine.radar import DiscoveryRadar
from providers.base import Tweet, BaseTwitterProvider


class DummyProvider(BaseTwitterProvider):
    def __init__(self, tweets):
        self._tweets = tweets

    def get_tweet(self, tweet_id: str):
        return None

    def post_reply(self, text: str, reply_to_tweet_id: str, media_paths=None):
        return {}

    def search_recent_tweets(self, query: str, limit: int = 10):
        return self._tweets


def test_radar_skips_arabic_and_non_english_tweets():
    """Verify DiscoveryRadar rejects tweets in Arabic or non-English lang tags at ingestion."""
    now = datetime.now(timezone.utc)
    tweets = [
        # 1. Valid English tweet
        Tweet(id="101", text="Important update on humanitarian aid in Gaza.", author_handle="user1", created_at=now, raw_data={"lang": "en"}),
        # 2. Arabic text tweet (even without lang tag)
        Tweet(id="102", text="مساعدات إنسانية جديدة تدخل غزة اليوم", author_handle="user2", created_at=now, raw_data={}),
        # 3. Non-English lang tag (e.g. Spanish)
        Tweet(id="103", text="Noticias importantes sobre la situacion", author_handle="user3", created_at=now, raw_data={"lang": "es"}),
        # 4. English tweet with no explicit lang tag (und / fallback)
        Tweet(id="104", text="Ceasefire negotiations ongoing in Middle East.", author_handle="user4", created_at=now, raw_data={"lang": "und"}),
    ]

    mock_repo = MagicMock()
    mock_repo.is_tweet_processed.return_value = False
    mock_repo.enqueue_tweet.return_value = True

    radar = DiscoveryRadar(repository=mock_repo)
    provider = DummyProvider(tweets)

    results = radar.scan_keywords(
        provider=provider,
        keywords=["Gaza"],
        combine_queries=False,
        dry_run=True,
        min_virality_score=0.0
    )

    enqueued_ids = [item["tweet_id"] for item in results]
    assert "101" in enqueued_ids
    assert "104" in enqueued_ids
    assert "102" not in enqueued_ids  # Arabic text rejected
    assert "103" not in enqueued_ids  # 'es' language rejected

    assert radar.last_scan_stats is not None
    # Skipped language count should be 2
    query_stat = radar.last_scan_stats["queries"][0]
    assert query_stat.get("skipped_language") == 2
