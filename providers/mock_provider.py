"""Mock Twitter Provider for safe local testing and development."""

from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any
from providers.base import BaseTwitterProvider, Tweet


class MockTwitterProvider(BaseTwitterProvider):
    """Simulates Twitter search and posting without network requests."""

    def __init__(self):
        now = datetime.now(timezone.utc)
        self.mock_tweets: List[Tweet] = [
            Tweet(
                id="mock_viral_101",
                text="Israel has completely blocked all food and water aid from entering Gaza for the last 6 months.",
                author_handle="critique_daily",
                created_at=now - timedelta(minutes=45),
                likes=1200,
                retweets=450,
                replies=310,
                conversation_id="mock_viral_101"
            ),
            Tweet(
                id="mock_low_202",
                text="Just had lunch in Tel Aviv, sunny day.",
                author_handle="tourist_alice",
                created_at=now - timedelta(minutes=15),
                likes=2,
                retweets=0,
                replies=1,
                conversation_id="mock_low_202"
            ),
            Tweet(
                id="mock_toxic_303",
                text="You are all disgusting evil murderers and zionist pigs shut up!",
                author_handle="hater_999",
                created_at=now - timedelta(minutes=20),
                likes=80,
                retweets=25,
                replies=12,
                conversation_id="mock_viral_101",
                in_reply_to_tweet_id="mock_bot_reply_001"
            ),
            Tweet(
                id="mock_dialogue_404",
                text="Where is the actual documentation showing COGAT humanitarian aid statistics?",
                author_handle="skeptic_observer",
                created_at=now - timedelta(minutes=10),
                likes=350,
                retweets=90,
                replies=45,
                conversation_id="mock_viral_101",
                in_reply_to_tweet_id="mock_bot_reply_001"
            )
        ]
        self.posted_replies: List[Dict[str, Any]] = []

    def search_recent_tweets(self, query: str, limit: int = 10) -> List[Tweet]:
        """Return subset of mock tweets."""
        return self.mock_tweets[:limit]

    def post_reply(
        self,
        text: str,
        reply_to_tweet_id: str,
        media_paths: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Simulate posting a reply."""
        response = {
            "success": True,
            "id": f"mock_reply_{len(self.posted_replies) + 1}",
            "reply_to": reply_to_tweet_id,
            "text": text,
            "media_paths": media_paths or [],
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        self.posted_replies.append(response)
        return response

    def get_tweet(self, tweet_id: str) -> Optional[Tweet]:
        """Find a mock tweet by ID."""
        for t in self.mock_tweets:
            if t.id == tweet_id:
                return t
        return None
