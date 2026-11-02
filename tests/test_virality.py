from datetime import datetime, timezone, timedelta
from providers.base import Tweet
from engine.virality import calculate_virality_score, is_viral_candidate, get_virality_tier


def test_virality_score_calculation():
    now = datetime.now(timezone.utc)
    # Tweet created 30 minutes ago, with 100 likes, 50 retweets, 20 replies
    # Weighted engagements = 100 * 1.0 + 50 * 2.0 + 20 * 1.5 = 100 + 100 + 30 = 230
    # Time denominator = 30 + 10 = 40
    # Expected score = 230 / 40 = 5.75
    tweet = Tweet(
        id="test_1",
        text="Test tweet",
        author_handle="user1",
        created_at=now - timedelta(minutes=30),
        likes=100,
        retweets=50,
        replies=20
    )

    score = calculate_virality_score(tweet)
    assert score == 5.75
    assert is_viral_candidate(tweet, threshold=5.0) is True
    assert is_viral_candidate(tweet, threshold=6.0) is False


def test_low_virality_tweet():
    now = datetime.now(timezone.utc)
    tweet = Tweet(
        id="test_low",
        text="Quiet tweet",
        author_handle="user2",
        created_at=now - timedelta(minutes=60),
        likes=5,
        retweets=0,
        replies=0
    )
    score = calculate_virality_score(tweet)
    assert score < 1.0
    assert is_viral_candidate(tweet, threshold=5.0) is False


def test_virality_tiers():
    now = datetime.now(timezone.utc)

    # Explosive virality: 1000 likes, 500 retweets, 300 replies, 20 mins ago
    # (1000 + 1000 + 450) / 30 = 2450 / 30 = 81.67
    explosive_tweet = Tweet(
        id="test_explosive",
        text="Breaking news",
        author_handle="influencer",
        created_at=now - timedelta(minutes=20),
        likes=1000,
        retweets=500,
        replies=300
    )
    assert get_virality_tier(explosive_tweet) == "VIRAL_EXPLOSIVE"

    # Low traction
    low_tweet = Tweet(
        id="test_low_2",
        text="Random thought",
        author_handle="nobody",
        created_at=now - timedelta(minutes=50),
        likes=2,
        retweets=0,
        replies=0
    )
    assert get_virality_tier(low_tweet) == "LOW_TRACTION"


def test_sustained_viral_tweets_at_11_and_20_hours():
    """Verify 11-hour and 20-hour viral tweets pass the 5.0 threshold via hybrid sustained scoring."""
    now = datetime.now(timezone.utc)

    # 11-hour-old viral tweet (660 mins) with 450 likes, 120 retweets, 40 replies (weighted = 750)
    tweet_11h = Tweet(
        id="viral_11h",
        text="Viral claim from 11 hours ago",
        author_handle="big_account",
        created_at=now - timedelta(hours=11),
        likes=450,
        retweets=120,
        replies=40,
    )
    score_11h = calculate_virality_score(tweet_11h)
    assert score_11h >= 5.0
    assert is_viral_candidate(tweet_11h, threshold=5.0) is True
    assert get_virality_tier(tweet_11h) in ("VIRAL_EMERGING", "VIRAL_HIGH", "VIRAL_EXPLOSIVE")

    # 20-hour-old viral tweet (1200 mins) with 650 likes, 180 retweets, 60 replies (weighted = 1100)
    tweet_20h = Tweet(
        id="viral_20h",
        text="Viral claim from 20 hours ago",
        author_handle="big_account_2",
        created_at=now - timedelta(hours=20),
        likes=650,
        retweets=180,
        replies=60,
    )
    score_20h = calculate_virality_score(tweet_20h)
    assert score_20h >= 5.0
    assert is_viral_candidate(tweet_20h, threshold=5.0) is True

    # Low-engagement 11-hour-old tweet (20 likes, 2 RTs) should still be rejected (< 5.0)
    low_11h = Tweet(
        id="low_11h",
        text="Old non-viral tweet",
        author_handle="small_user",
        created_at=now - timedelta(hours=11),
        likes=20,
        retweets=2,
        replies=1,
    )
    assert calculate_virality_score(low_11h) < 1.0
    assert is_viral_candidate(low_11h, threshold=5.0) is False
