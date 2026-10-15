"""Virality momentum scoring engine based on PRD v2.0 formula."""

from providers.base import Tweet


def calculate_virality_score(tweet: Tweet) -> float:
    """
    Calculate momentum score based on PRD v2.0 Section 4:
    Score = (Likes * 1.0 + Retweets * 2.0 + Replies * 1.5) / (Age in Minutes + 10)
    """
    weighted_engagements = (
        (tweet.likes * 1.0) +
        (tweet.retweets * 2.0) +
        (tweet.replies * 1.5)
    )
    time_denominator = max(0.0, tweet.age_in_minutes) + 10.0
    return round(weighted_engagements / time_denominator, 2)


def get_virality_tier(tweet: Tweet) -> str:
    """Classify tweet momentum into actionable priority tiers."""
    score = calculate_virality_score(tweet)
    if score >= 20.0:
        return "VIRAL_EXPLOSIVE"
    elif score >= 10.0:
        return "VIRAL_HIGH"
    elif score >= 5.0:
        return "VIRAL_EMERGING"
    return "LOW_TRACTION"


def is_viral_candidate(tweet: Tweet, threshold: float = 5.0) -> bool:
    """Return True if virality momentum score meets or exceeds threshold."""
    score = calculate_virality_score(tweet)
    return score >= threshold
