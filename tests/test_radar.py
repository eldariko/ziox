from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any
from unittest.mock import MagicMock, patch
from config.settings import Settings
from database.repository import Repository
from providers.base import (
    BaseTwitterProvider,
    Tweet,
    ScannerCircuitBreakerError,
    classify_scanner_exception,
)
from providers.mock_provider import MockTwitterProvider
from engine.radar import DiscoveryRadar, extract_tweet_id, calculate_search_jitter


def test_phase_a_settings_defaults():
    """Verify Task 1.1 & 1.2: Phase A scanner safety settings and max_tweet_age_hours load with expected defaults."""
    s = Settings(_env_file=None)
    assert s.combine_search_queries is True
    assert s.max_keywords_per_query == 6
    assert s.min_search_delay_seconds == 6.0
    assert s.max_search_delay_seconds == 15.0
    assert s.scanner_cooldown_minutes == 720
    assert s.max_tweet_age_hours == 24.0


def test_extract_tweet_id():
    assert extract_tweet_id("1845123456789") == "1845123456789"
    assert extract_tweet_id("https://x.com/user/status/1845123456789") == "1845123456789"
    assert extract_tweet_id("https://twitter.com/user/status/1845123456789?s=20") == "1845123456789"
    assert extract_tweet_id("not_a_valid_tweet") is None


def test_radar_enqueue_manual(tmp_path):
    db_file = str(tmp_path / "test_radar.db")
    repo = Repository(db_file)
    radar = DiscoveryRadar(repo)

    res = radar.enqueue_manual(
        url_or_id="https://x.com/critic/status/987654321",
        author_handle="@critic",
        tweet_text="False factual claim about Gaza crossing.",
        likes=300,
        retweets=150,
        replies=50
    )

    assert res["tweet_id"] == "987654321"
    assert res["author"] == "critic"
    assert res["newly_enqueued"] is True
    assert res["status"] == "DISCOVERED"

    # Enqueue same ID again -> should return ALREADY_EXISTS
    res_repeat = radar.enqueue_manual(
        url_or_id="987654321",
        author_handle="critic",
        tweet_text="Duplicate"
    )
    assert res_repeat["newly_enqueued"] is False
    assert res_repeat["status"] == "ALREADY_EXISTS"

    # Check pending queue
    pending = repo.get_pending_tweets(limit=10)
    assert len(pending) == 1
    assert pending[0]["tweet_id"] == "987654321"


def test_radar_scan_keywords(tmp_path):
    db_file = str(tmp_path / "test_radar_scan.db")
    repo = Repository(db_file)
    radar = DiscoveryRadar(repo)
    provider = MockTwitterProvider()

    discovered = radar.scan_keywords(
        provider=provider,
        keywords=["Israel", "aid"],
        limit_per_keyword=5,
        min_virality_score=0.0
    )

    assert len(discovered) > 0
    pending = repo.get_pending_tweets(limit=10)
    assert len(pending) == len(discovered)


def test_radar_filters_tweets_older_than_max_tweet_age_hours(tmp_path):
    """Verify tweets older than max_tweet_age_hours (e.g. 30h > 24h) are skipped while 15h viral tweets are enqueued."""
    db_file = str(tmp_path / "test_radar_age.db")
    repo = Repository(db_file)
    radar = DiscoveryRadar(repo)

    now = datetime.now(timezone.utc)

    class _AgeTestProvider(BaseTwitterProvider):
        def search_recent_tweets(self, query: str, limit: int = 10) -> List[Tweet]:
            return [
                Tweet(
                    id="tweet_15h_viral",
                    text="Viral 15h post about Israel",
                    author_handle="user15",
                    created_at=now - timedelta(hours=15),
                    likes=500,
                    retweets=150,
                    replies=50,
                ),
                Tweet(
                    id="tweet_30h_stale",
                    text="Stale 30h post about Israel",
                    author_handle="user30",
                    created_at=now - timedelta(hours=30),
                    likes=5000,
                    retweets=2000,
                    replies=500,
                ),
            ]

        def post_reply(self, text: str, reply_to_tweet_id: str, media_paths: Optional[List[str]] = None) -> Dict[str, Any]:
            return {}

        def get_tweet(self, tweet_id: str) -> Optional[Tweet]:
            return None

    discovered = radar.scan_keywords(
        provider=_AgeTestProvider(),
        keywords=["Israel"],
        limit_per_keyword=10,
        min_virality_score=5.0,
        max_tweet_age_hours=24.0,
        dry_run=True,
    )

    assert len(discovered) == 1
    assert discovered[0]["tweet_id"] == "tweet_15h_viral"


def test_twikit_search_recent_tweets_blends_top_and_latest():
    """Verify TwikitTwitterProvider queries both Top and Latest tabs and deduplicates by tweet ID."""
    from providers import twikit_provider

    now = datetime.now(timezone.utc)

    def _make_raw(tid: str, text: str, likes: int):
        raw = MagicMock()
        raw.id = tid
        raw.text = text
        raw.created_at_datetime = now - timedelta(hours=11)
        raw.favorite_count = likes
        raw.retweet_count = 100
        raw.reply_count = 40
        raw.conversation_id = tid
        raw.in_reply_to = None
        raw.user = MagicMock()
        raw.user.screen_name = f"author_{tid}"
        return raw

    top_list = [_make_raw("101", "Top viral 11h post", 450), _make_raw("102", "Shared post", 300)]
    latest_list = [_make_raw("102", "Shared post", 300), _make_raw("103", "Fresh latest post", 80)]

    provider = object.__new__(twikit_provider.TwikitTwitterProvider)
    provider.client = MagicMock()

    calls = []

    def fake_run_coro(coro):
        # We inspect mock call args recorded on provider.client.search_tweet
        last_call = provider.client.search_tweet.call_args
        product = last_call.kwargs.get("product")
        calls.append(product)
        if product == "Top":
            return top_list
        return latest_list

    with patch.object(twikit_provider, "_run_coro", side_effect=fake_run_coro):
        results = provider.search_recent_tweets("Israel", limit=10)

    assert calls == ["Top", "Latest"]
    assert [t.id for t in results] == ["101", "102", "103"]


def test_build_consolidated_queries_script_grouping():
    """Verify Task 1.3: English and Arabic keywords are grouped separately into Boolean OR queries."""
    keywords = [
        "Israel",
        "Gaza",
        "IDF",
        "Zionism",
        "Hostages",
        "Middle East",
        "إسرائيل",
        "غزة",
        "مساعدات غزة",
    ]
    queries = DiscoveryRadar.build_consolidated_queries(keywords, max_per_query=6)
    assert len(queries) == 2
    assert queries[0] == '("Israel" OR "Gaza" OR "IDF" OR "Zionism" OR "Hostages" OR "Middle East")'
    assert queries[1] == '("إسرائيل" OR "غزة" OR "مساعدات غزة")'


def test_calculate_search_jitter_bounds():
    """Verify Task 1.3: Gaussian search jitter stays strictly within [min_delay, max_delay]."""
    for _ in range(50):
        delay = calculate_search_jitter(6.0, 15.0)
        assert 6.0 <= delay <= 15.0


def test_classify_scanner_exception():
    """Verify Task 1.2: Rate limits (429), auth errors (401/403), and account locks are classified properly."""
    err_429 = classify_scanner_exception(RuntimeError("HTTP 429 Too Many Requests: Rate limit exceeded"))
    assert isinstance(err_429, ScannerCircuitBreakerError)
    assert err_429.status_code == 429
    assert err_429.reason == "RATE_LIMIT_429"

    err_401 = classify_scanner_exception(RuntimeError("401 Unauthorized: Could not authenticate you"))
    assert isinstance(err_401, ScannerCircuitBreakerError)
    assert err_401.status_code == 401
    assert err_401.reason == "AUTH_FAILURE_401"

    err_lock = classify_scanner_exception(RuntimeError("Error 326: Your account is temporarily locked (Arkose challenge)"))
    assert isinstance(err_lock, ScannerCircuitBreakerError)
    assert err_lock.reason == "ACCOUNT_LOCKED_OR_CHALLENGE"

    # Generic transient network error should NOT trip the account circuit breaker
    err_generic = classify_scanner_exception(ConnectionError("Connection reset by peer"))
    assert err_generic is None


class _CircuitBreakerStubProvider(BaseTwitterProvider):
    """Stub provider that raises a 429 rate-limit error on the first query and tracks call count."""

    def __init__(self):
        self.queries_called: List[str] = []

    def search_recent_tweets(self, query: str, limit: int = 10) -> List[Tweet]:
        self.queries_called.append(query)
        raise ScannerCircuitBreakerError("Rate limit 429 on search_tweet", status_code=429, reason="RATE_LIMIT_429")

    def post_reply(self, text: str, reply_to_tweet_id: str, media_paths: Optional[List[str]] = None) -> Dict[str, Any]:
        return {}

    def get_tweet(self, tweet_id: str) -> Optional[Tweet]:
        return None


def test_radar_circuit_breaker_aborts_immediately(tmp_path):
    """Verify Task 1.2 & 1.3: When query 1 triggers a 429 circuit breaker, Radar aborts immediately without running query 2."""
    db_file = str(tmp_path / "test_cb.db")
    repo = Repository(db_file)
    radar = DiscoveryRadar(repo)
    stub_provider = _CircuitBreakerStubProvider()
    triggered_errors: List[ScannerCircuitBreakerError] = []

    keywords = ["Israel", "Gaza", "إسرائيل", "غزة"]
    results = radar.scan_keywords(
        provider=stub_provider,
        keywords=keywords,
        combine_queries=True,
        max_keywords_per_query=2,
        dry_run=True,
        on_circuit_breaker=lambda err: triggered_errors.append(err),
    )

    assert results == []
    # Only the first query ("Israel" OR "Gaza") was attempted; the second Arabic query was aborted!
    assert len(stub_provider.queries_called) == 1
    assert radar.last_circuit_breaker_error is not None
    assert radar.last_circuit_breaker_error.reason == "RATE_LIMIT_429"
    assert len(triggered_errors) == 1

    logs = repo.get_recent_logs(limit=5)
    assert len(logs) == 1
    assert logs[0]["status"] == "ABORTED_CIRCUIT_BREAKER_RATE_LIMIT_429"
