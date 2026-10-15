"""Discovery Radar module for finding and queuing viral candidate tweets on X."""

import re
import time
import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from providers.base import Tweet, BaseTwitterProvider
from database.repository import Repository
from engine.virality import calculate_virality_score, get_virality_tier

logger = logging.getLogger(__name__)

# Matches standard X / Twitter status URLs (with or without queries) or pure numeric IDs
TWEET_URL_REGEX = re.compile(
    r"(?:https?://(?:www\.)?(?:twitter\.com|x\.com)/[A-Za-z0-9_]+/status(?:es)?/)?(\d+)",
    re.IGNORECASE
)


def extract_tweet_id(url_or_id: str) -> Optional[str]:
    """
    Extract clean numeric tweet ID from a URL or raw ID string.
    Examples:
      - 'https://x.com/username/status/1845123456789' -> '1845123456789'
      - 'https://twitter.com/i/web/status/1845123456789?s=20' -> '1845123456789'
      - '1845123456789' -> '1845123456789'
    """
    cleaned = url_or_id.strip()
    match = TWEET_URL_REGEX.search(cleaned)
    if match:
        return match.group(1)
    return None


class DiscoveryRadar:
    """Manages viral post discovery, scoring, and queue ingestion."""

    def __init__(self, repository: Repository):
        self.repo = repository

    def enqueue_manual(
        self,
        url_or_id: str,
        author_handle: str = "unknown",
        tweet_text: str = "",
        likes: int = 0,
        retweets: int = 0,
        replies: int = 0,
        parent_tweet_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Ingest a specific tweet URL or ID manually into the queue.
        Calculates virality score and stores with status='DISCOVERED'.
        """
        tweet_id = extract_tweet_id(url_or_id)
        if not tweet_id:
            raise ValueError(f"Invalid tweet URL or ID: {url_or_id}")

        tweet_obj = Tweet(
            id=tweet_id,
            text=tweet_text,
            author_handle=author_handle.lstrip("@"),
            created_at=datetime.now(timezone.utc),
            likes=likes,
            retweets=retweets,
            replies=replies,
            in_reply_to_tweet_id=parent_tweet_id
        )

        virality_score = calculate_virality_score(tweet_obj)
        tier = get_virality_tier(tweet_obj)

        newly_enqueued = self.repo.enqueue_tweet(
            tweet_id=tweet_id,
            author_handle=tweet_obj.author_handle,
            tweet_text=tweet_text,
            virality_score=virality_score,
            parent_tweet_id=parent_tweet_id
        )

        return {
            "tweet_id": tweet_id,
            "author": tweet_obj.author_handle,
            "virality_score": virality_score,
            "tier": tier,
            "newly_enqueued": newly_enqueued,
            "status": "DISCOVERED" if newly_enqueued else "ALREADY_EXISTS"
        }

    def scan_keywords(
        self,
        provider: BaseTwitterProvider,
        keywords: List[str],
        limit_per_keyword: int = 5,
        min_virality_score: float = 0.0
    ) -> List[Dict[str, Any]]:
        """
        Scan recent posts across search keywords using a provider,
        calculate virality velocity, and enqueue candidate posts.
        """
        enqueued_items: List[Dict[str, Any]] = []

        for idx, keyword in enumerate(keywords):
            if idx > 0:
                time.sleep(1.2)
            try:
                tweets = provider.search_recent_tweets(keyword, limit=limit_per_keyword)
                for tweet in tweets:
                    if self.repo.is_tweet_processed(tweet.id):
                        continue

                    score = calculate_virality_score(tweet)
                    if score < min_virality_score:
                        continue

                    is_new = self.repo.enqueue_tweet(
                        tweet_id=tweet.id,
                        author_handle=tweet.author_handle,
                        tweet_text=tweet.text,
                        virality_score=score,
                        parent_tweet_id=tweet.in_reply_to_tweet_id
                    )

                    if is_new:
                        tier = get_virality_tier(tweet)
                        enqueued_items.append({
                            "tweet_id": tweet.id,
                            "author": tweet.author_handle,
                            "text": tweet.text,
                            "virality_score": score,
                            "tier": tier,
                            "keyword": keyword
                        })
            except Exception as e:
                logger.error(f"Radar failed scanning keyword '{keyword}': {e}")
                continue

        return enqueued_items
