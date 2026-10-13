"""Zernio Twitter API Provider."""

import httpx
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from providers.base import BaseTwitterProvider, Tweet


class ZernioTwitterProvider(BaseTwitterProvider):
    """Integrates with Zernio unified social media API for X (Twitter)."""

    BASE_URL = "https://api.zernio.com/v1"

    def __init__(self, api_key: str, twitter_account_id: str):
        self.api_key = api_key
        self.twitter_account_id = twitter_account_id
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    def search_recent_tweets(self, query: str, limit: int = 10) -> List[Tweet]:
        """Search recent tweets via Zernio endpoint."""
        url = f"{self.BASE_URL}/twitter/search"
        params = {"query": query, "limit": limit}

        with httpx.Client(timeout=15.0) as client:
            response = client.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            data = response.json()

        tweets: List[Tweet] = []
        raw_items = data.get("data", []) or data.get("tweets", [])
        for item in raw_items:
            created_str = item.get("created_at") or item.get("createdAt")
            created_dt = datetime.now(timezone.utc)
            if created_str:
                try:
                    created_dt = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
                except ValueError:
                    pass

            metrics = item.get("public_metrics", {})
            tweets.append(
                Tweet(
                    id=str(item.get("id")),
                    text=item.get("text", ""),
                    author_handle=item.get("author_username", item.get("username", "unknown")),
                    created_at=created_dt,
                    likes=metrics.get("like_count", item.get("likes", 0)),
                    retweets=metrics.get("retweet_count", item.get("retweets", 0)),
                    replies=metrics.get("reply_count", item.get("replies", 0)),
                    conversation_id=item.get("conversation_id"),
                    in_reply_to_tweet_id=item.get("in_reply_to_status_id"),
                    raw_data=item
                )
            )
        return tweets

    def post_reply(
        self,
        text: str,
        reply_to_tweet_id: str,
        media_paths: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Publish reply tweet via Zernio."""
        url = f"{self.BASE_URL}/posts"
        payload = {
            "content": text,
            "publishNow": True,
            "platforms": [
                {
                    "platform": "twitter",
                    "accountId": self.twitter_account_id,
                    "platformSpecificData": {
                        "replyToPostId": reply_to_tweet_id
                    }
                }
            ]
        }

        with httpx.Client(timeout=20.0) as client:
            response = client.post(url, headers=self.headers, json=payload)
            response.raise_for_status()
            return response.json()

    def get_tweet(self, tweet_id: str) -> Optional[Tweet]:
        """Fetch tweet by ID via Zernio."""
        url = f"{self.BASE_URL}/twitter/lookup"
        params = {"id": tweet_id}

        with httpx.Client(timeout=15.0) as client:
            response = client.get(url, headers=self.headers, params=params)
            if response.status_code == 404:
                return None
            response.raise_for_status()
            data = response.json()

        item = data.get("data", data)
        if not item or not item.get("id"):
            return None

        created_str = item.get("created_at")
        created_dt = datetime.now(timezone.utc)
        if created_str:
            try:
                created_dt = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
            except ValueError:
                pass

        metrics = item.get("public_metrics", {})
        return Tweet(
            id=str(item.get("id")),
            text=item.get("text", ""),
            author_handle=item.get("author_username", "unknown"),
            created_at=created_dt,
            likes=metrics.get("like_count", 0),
            retweets=metrics.get("retweet_count", 0),
            replies=metrics.get("reply_count", 0),
            conversation_id=item.get("conversation_id"),
            raw_data=item
        )
