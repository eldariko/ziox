from datetime import datetime, timezone, timedelta
from providers.base import Tweet
from engine.virality import calculate_virality_score, is_viral_candidate


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
    # 5 / (60 + 10) = 5 / 70 = 0.07
    assert score < 1.0
    assert is_viral_candidate(tweet, threshold=5.0) is False
