"""Discovery Radar module for finding and queuing viral candidate tweets on X."""

import random
import re
import time
import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Callable
from providers.base import (
    Tweet,
    BaseTwitterProvider,
    ScannerCircuitBreakerError,
    classify_scanner_exception,
)
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


def calculate_search_jitter(min_delay: float, max_delay: float) -> float:
    """
    Calculate human-like Gaussian search delay bounded strictly between min_delay and max_delay.
    """
    if min_delay <= 0 and max_delay <= 0:
        return 0.0
    if min_delay >= max_delay:
        return float(max(0.0, min_delay))
    mean = (min_delay + max_delay) / 2.0
    std_dev = (max_delay - min_delay) / 6.0
    delay = random.gauss(mean, std_dev)
    return max(min_delay, min(max_delay, delay))


class DiscoveryRadar:
    """Manages viral post discovery, scoring, and queue ingestion."""

    def __init__(self, repository: Repository):
        self.repo = repository
        self.last_circuit_breaker_error: Optional[ScannerCircuitBreakerError] = None

    @staticmethod
    def _is_arabic_term(term: str) -> bool:
        """Return True if the keyword contains Arabic script characters."""
        return any("\u0600" <= ch <= "\u06ff" for ch in term)

    @staticmethod
    def _format_keyword_for_or(term: str) -> str:
        """Wrap multi-word or quoted keywords cleanly in double quotes for X Boolean OR syntax."""
        cleaned = term.strip().strip('"')
        if not cleaned:
            return ""
        return f'"{cleaned}"'

    @classmethod
    def build_consolidated_queries(
        cls,
        keywords: List[str],
        max_per_query: int = 6
    ) -> List[str]:
        """
        Consolidate search keywords into script-grouped (English/Latin vs. Arabic)
        Boolean OR queries up to `max_per_query` terms per query.
        Example:
          ['Israel', 'Gaza', 'Middle East', 'إسرائيل', 'مساعدات غزة']
          -> [
               '("Israel" OR "Gaza" OR "Middle East")',
               '("إسرائيل" OR "مساعدات غزة")'
             ]
        """
        if max_per_query <= 1:
            return [k.strip() for k in keywords if k.strip()]

        latin_terms: List[str] = []
        arabic_terms: List[str] = []

        for kw in keywords:
            cleaned = kw.strip()
            if not cleaned:
                continue
            if cls._is_arabic_term(cleaned):
                arabic_terms.append(cleaned)
            else:
                latin_terms.append(cleaned)

        queries: List[str] = []
        for group in (latin_terms, arabic_terms):
            for i in range(0, len(group), max_per_query):
                chunk = group[i:i + max_per_query]
                if len(chunk) == 1:
                    queries.append(cls._format_keyword_for_or(chunk[0]))
                elif chunk:
                    joined = " OR ".join(cls._format_keyword_for_or(t) for t in chunk)
                    queries.append(f"({joined})")

        return queries

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
        min_virality_score: float = 0.0,
        combine_queries: bool = True,
        max_keywords_per_query: int = 6,
        min_search_delay_seconds: float = 6.0,
        max_search_delay_seconds: float = 15.0,
        dry_run: bool = True,
        on_circuit_breaker: Optional[Callable[[ScannerCircuitBreakerError], None]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Scan recent posts across search keywords using a provider,
        calculate virality velocity, and enqueue candidate posts.

        Phase A Safety Upgrades:
        1. Consolidates keywords into script-grouped Boolean OR queries when `combine_queries=True`.
        2. Replaces static 1.2s sleep with Gaussian jitter (`min_search_delay_seconds`..`max_search_delay_seconds`).
        3. Immediately aborts the scan cycle if a `ScannerCircuitBreakerError` (401/403/429/Lock) occurs.
        """
        self.last_circuit_breaker_error = None
        enqueued_items: List[Dict[str, Any]] = []

        queries_to_run = (
            self.build_consolidated_queries(keywords, max_per_query=max_keywords_per_query)
            if combine_queries
            else [k.strip() for k in keywords if k.strip()]
        )

        for idx, query_str in enumerate(queries_to_run):
            if idx > 0:
                delay = calculate_search_jitter(min_search_delay_seconds, max_search_delay_seconds)
                if dry_run or delay <= 0:
                    logger.info(f"[RADAR STEALTH] Simulated {delay:.1f}s Gaussian search delay before query {idx + 1}.")
                else:
                    logger.info(f"[RADAR STEALTH] Sleeping {delay:.1f}s before query {idx + 1} to protect scanner profile...")
                    time.sleep(delay)

            try:
                tweets = provider.search_recent_tweets(query_str, limit=limit_per_keyword)
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
                            "keyword": query_str
                        })
            except Exception as e:
                cb_err = classify_scanner_exception(e)
                if cb_err is not None:
                    self.last_circuit_breaker_error = cb_err
                    logger.critical(
                        f"[RADAR CIRCUIT BREAKER] Halting scan immediately to protect X profile! "
                        f"Reason: {cb_err.reason} | Details: {cb_err}"
                    )
                    self.repo.log_run(
                        tweets_scanned=len(enqueued_items),
                        replies_sent=0,
                        status=f"ABORTED_CIRCUIT_BREAKER_{cb_err.reason}",
                        error_message=str(cb_err)
                    )
                    if on_circuit_breaker is not None:
                        try:
                            on_circuit_breaker(cb_err)
                        except Exception as hook_err:
                            logger.error(f"Circuit breaker callback failed: {hook_err}")
                    break

                logger.error(f"Radar failed scanning query '{query_str}': {e}", exc_info=True)
                continue

        return enqueued_items
