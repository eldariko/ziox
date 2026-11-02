"""Virality momentum scoring engine with hybrid sustained-engagement scoring for 1-24h viral posts."""

from providers.base import Tweet


def calculate_virality_score(tweet: Tweet) -> float:
    """
    Calculate hybrid virality momentum score:
    1. Instantaneous velocity:
       Velocity = (Likes * 1.0 + Retweets * 2.0 + Replies * 1.5) / (Age in Minutes + 10)
    2. Sustained viral impact (for posts between 1 and 24 hours old, i.e., 60..1440 mins):
       Sustained = Weighted Engagements / ((Age in Hours ** 0.65) * 18.0)
       This ensures viral posts that are 11 or 20 hours old with strong engagement
       are not discarded by harsh linear minute division.
    """
    weighted_engagements = (
        (tweet.likes * 1.0) +
        (tweet.retweets * 2.0) +
        (tweet.replies * 1.5)
    )
    age_mins = max(0.0, tweet.age_in_minutes)
    velocity_score = weighted_engagements / (age_mins + 10.0)

    if 60.0 <= age_mins <= 1440.0:
        age_hours = age_mins / 60.0
        sustained_score = weighted_engagements / ((age_hours ** 0.65) * 18.0)
        return round(max(velocity_score, sustained_score), 2)

    return round(velocity_score, 2)


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
