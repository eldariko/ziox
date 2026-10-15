"""Twikit-based direct Twitter/X provider using session authentication."""

import os
import json
import asyncio
import logging
import threading
import concurrent.futures
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from providers.base import BaseTwitterProvider, Tweet

logger = logging.getLogger(__name__)


def _apply_twikit_patches():
    """Apply compatibility patches to Twikit for X's updated Webpack chunk structure and user schemas."""
    try:
        import re
        import twikit.x_client_transaction.transaction as tx_mod
        import twikit.user
        import twikit.guest.user

        # 1. Update regexes for X's 2-step Webpack chunk table and JS byte indices
        tx_mod.ON_DEMAND_FILE_REGEX = re.compile(
            r',(\d+):["\']ondemand\.s["\']', flags=(re.VERBOSE | re.MULTILINE)
        )
        tx_mod.ON_DEMAND_HASH_PATTERN = r',{}:["\']([0-9a-f]+)["\']'
        tx_mod.INDICES_REGEX = re.compile(r'\[(\d+)\],\s*16')

        # 2. Reset home_page_response on failure so subsequent requests can re-initialize properly
        orig_init = tx_mod.ClientTransaction.init
        async def safe_init(self, session, headers):
            try:
                await orig_init(self, session, headers)
            except Exception:
                self.home_page_response = None
                raise
            tx_mod.ClientTransaction.init = safe_init

        # 3. Patch get_indices to resolve ondemand.s via chunk index -> chunk hash
        async def patched_get_indices(self, home_page_response, session, headers):
            key_byte_indices = []
            response = self.validate_response(
                home_page_response) or self.home_page_response
            on_demand_match = tx_mod.ON_DEMAND_FILE_REGEX.search(str(response))
            if on_demand_match:
                chunk_index = on_demand_match.group(1)
                hash_match = re.search(
                    tx_mod.ON_DEMAND_HASH_PATTERN.format(chunk_index), str(response)
                )
                if hash_match:
                    file_hash = hash_match.group(1)
                    on_demand_file_url = f"https://abs.twimg.com/responsive-web/client-web/ondemand.s.{file_hash}a.js"
                    on_demand_file_response = await session.request(
                        method="GET", url=on_demand_file_url, headers=headers
                    )
                    for item in tx_mod.INDICES_REGEX.finditer(on_demand_file_response.text):
                        key_byte_indices.append(item.group(1))
            if not key_byte_indices:
                raise Exception("Couldn't get KEY_BYTE indices")
            key_byte_indices = list(map(int, key_byte_indices))
            return key_byte_indices[0], key_byte_indices[1:]

        tx_mod.ClientTransaction.get_indices = patched_get_indices

        # 4. Guard missing user schema fields (e.g. pinned_tweet_ids_str, withheld_in_countries, description.urls)
        orig_user_init = twikit.user.User.__init__
        def safe_user_init(self, client, data):
            legacy = data.get('legacy', {})
            if isinstance(legacy, dict):
                legacy.setdefault('pinned_tweet_ids_str', [])
                legacy.setdefault('withheld_in_countries', [])
                if 'entities' in legacy and isinstance(legacy['entities'], dict):
                    legacy['entities'].setdefault('description', {}).setdefault('urls', [])
            orig_user_init(self, client, data)
        twikit.user.User.__init__ = safe_user_init

        orig_guest_init = twikit.guest.user.User.__init__
        def safe_guest_init(self, client, data):
            legacy = data.get('legacy', {})
            if isinstance(legacy, dict):
                legacy.setdefault('pinned_tweet_ids_str', [])
                legacy.setdefault('withheld_in_countries', [])
                if 'entities' in legacy and isinstance(legacy['entities'], dict):
                    legacy['entities'].setdefault('description', {}).setdefault('urls', [])
            orig_guest_init(self, client, data)
        twikit.guest.user.User.__init__ = safe_guest_init
    except Exception as e:
        logger.warning(f"Could not apply Twikit compatibility patch: {e}")

_apply_twikit_patches()


class _LoopRunner:
    """Manages a persistent background event loop to execute Twikit async calls safely without closing httpx transports."""
    def __init__(self):
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    def _ensure_running(self):
        with self._lock:
            if self._thread is None or not self._thread.is_alive():
                ready = threading.Event()

                def _target():
                    self._loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(self._loop)
                    ready.set()
                    self._loop.run_forever()

                self._thread = threading.Thread(target=_target, daemon=True, name="TwikitLoopRunner")
                self._thread.start()
                ready.wait()

    def run(self, coro):
        self._ensure_running()
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result()


_loop_runner = _LoopRunner()


def _run_coro(coro):
    """Safely execute an asyncio coroutine on the persistent Twikit event loop."""
    return _loop_runner.run(coro)


class TwikitTwitterProvider(BaseTwitterProvider):
    """
    Direct authenticated X provider using Twikit.
    Bypasses official Twitter API third-party restrictions using session cookies (auth_token & ct0).
    """

    def __init__(
        self,
        auth_token: Optional[str] = None,
        ct0: Optional[str] = None,
        cookies_file: Optional[str] = "cookies.json"
    ):
        from twikit import Client
        self.client = Client("en-US")
        self._authenticated = False

        # 1. Attempt loading from file if it exists
        if cookies_file and os.path.exists(cookies_file):
            try:
                self.client.load_cookies(cookies_file)
                self._authenticated = True
                logger.info(f"Loaded X session cookies from {cookies_file}")
            except Exception as e:
                logger.warning(f"Could not load cookies from {cookies_file}: {e}")

        # 2. Alternatively, set direct auth cookies if provided
        if not self._authenticated and auth_token and ct0:
            self.client.set_cookies({
                "auth_token": auth_token,
                "ct0": ct0
            })
            self._authenticated = True
            logger.info("Configured X session via direct auth_token & ct0 cookies.")

    def get_tweet(self, tweet_id: str) -> Optional[Tweet]:
        """Fetch a specific tweet by ID directly from X."""
        try:
            raw_tweet = _run_coro(self.client.get_tweet_by_id(tweet_id))
            if not raw_tweet:
                return None

            author = "unknown"
            if hasattr(raw_tweet, "user") and raw_tweet.user:
                author = getattr(raw_tweet.user, "screen_name", "unknown")

            created_dt = getattr(raw_tweet, "created_at_datetime", None)
            if not created_dt:
                created_dt = datetime.now(timezone.utc)
            elif created_dt.tzinfo is None:
                created_dt = created_dt.replace(tzinfo=timezone.utc)

            text = getattr(raw_tweet, "text", "") or getattr(raw_tweet, "full_text", "")

            return Tweet(
                id=str(raw_tweet.id),
                text=text,
                author_handle=author,
                created_at=created_dt,
                likes=getattr(raw_tweet, "favorite_count", 0) or 0,
                retweets=getattr(raw_tweet, "retweet_count", 0) or 0,
                replies=getattr(raw_tweet, "reply_count", 0) or 0,
                conversation_id=str(getattr(raw_tweet, "conversation_id", raw_tweet.id)),
                in_reply_to_tweet_id=str(getattr(raw_tweet, "in_reply_to", "")) or None
            )
        except Exception as e:
            logger.error(f"Failed fetching tweet {tweet_id} via Twikit: {e}")
            return None

    def post_reply(
        self,
        text: str,
        reply_to_tweet_id: str,
        media_paths: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Post a direct in-thread reply to any tweet on X."""
        try:
            # Defensive guard against exceeding Twitter 280-char limit (Error 186)
            try:
                from engine.humanizer import Humanizer
                text = Humanizer.enforce_length_limit(text, max_length=280)
            except Exception as guard_err:
                logger.warning(f"Could not apply Humanizer length guard: {guard_err}")

            result = _run_coro(self.client.create_tweet(
                text=text,
                reply_to=reply_to_tweet_id
            ))
            return {
                "success": True,
                "id": str(getattr(result, "id", "")),
                "reply_to": reply_to_tweet_id,
                "text": text,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        except Exception as e:
            logger.error(f"Failed posting reply to {reply_to_tweet_id} via Twikit: {e}")
            raise

    def search_recent_tweets(self, query: str, limit: int = 10) -> List[Tweet]:
        """Search top recent tweets matching query on X."""
        try:
            results = _run_coro(self.client.search_tweet(query, product="Top", count=limit))
            tweets: List[Tweet] = []
            for raw_tweet in results:
                author = "unknown"
                if hasattr(raw_tweet, "user") and raw_tweet.user:
                    author = getattr(raw_tweet.user, "screen_name", "unknown")

                created_dt = getattr(raw_tweet, "created_at_datetime", None) or datetime.now(timezone.utc)
                if created_dt.tzinfo is None:
                    created_dt = created_dt.replace(tzinfo=timezone.utc)

                text = getattr(raw_tweet, "text", "") or getattr(raw_tweet, "full_text", "")
                tweets.append(
                    Tweet(
                        id=str(raw_tweet.id),
                        text=text,
                        author_handle=author,
                        created_at=created_dt,
                        likes=getattr(raw_tweet, "favorite_count", 0) or 0,
                        retweets=getattr(raw_tweet, "retweet_count", 0) or 0,
                        replies=getattr(raw_tweet, "reply_count", 0) or 0,
                        conversation_id=str(getattr(raw_tweet, "conversation_id", raw_tweet.id)),
                        in_reply_to_tweet_id=str(getattr(raw_tweet, "in_reply_to", "")) or None
                    )
                )
            return tweets[:limit]
        except Exception as e:
            logger.error(f"Failed searching tweets for '{query}' via Twikit: {e}")
            return []
