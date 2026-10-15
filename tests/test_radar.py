from database.repository import Repository
from providers.mock_provider import MockTwitterProvider
from engine.radar import DiscoveryRadar, extract_tweet_id


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
