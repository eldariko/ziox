"""Main Orchestrator pipeline connecting all zioX modules."""

import logging
from typing import Dict, Any, List
from config.settings import Settings
from database.repository import Repository
from providers.base import BaseTwitterProvider, Tweet
from engine.virality import calculate_virality_score, is_viral_candidate
from engine.thread_state import ThreadManager
from engine.grounding import GroundingEngine
from engine.humanizer import Humanizer

logger = logging.getLogger(__name__)


class BotOrchestrator:
    """Orchestrates tweet ingestion, filtering, fact-checking, and response dispatch."""

    def __init__(
        self,
        settings: Settings,
        repository: Repository,
        provider: BaseTwitterProvider,
        grounding_engine: GroundingEngine
    ):
        self.settings = settings
        self.repo = repository
        self.provider = provider
        self.grounding = grounding_engine
        self.thread_manager = ThreadManager(repository, max_turns=settings.max_thread_turns)

    def run_cycle(self) -> Dict[str, Any]:
        """
        Executes a single monitoring and engagement cycle.
        Returns a summary report of actions taken.
        """
        scanned_count = 0
        replies_sent = 0
        results: List[Dict[str, Any]] = []

        # Check monthly quota first
        current_monthly_count = self.repo.get_monthly_reply_count()
        if current_monthly_count >= self.settings.monthly_max_replies:
            msg = f"Monthly reply ceiling reached ({current_monthly_count}/{self.settings.monthly_max_replies}). Cycle aborted."
            logger.warning(msg)
            self.repo.log_run(0, 0, "ABORTED_QUOTA_EXCEEDED", msg)
            return {"status": "QUOTA_EXCEEDED", "scanned": 0, "replies": 0, "details": msg}

        # Search tweets for each keyword
        for keyword in self.settings.search_keywords:
            try:
                tweets = self.provider.search_recent_tweets(keyword, limit=5)
            except Exception as e:
                logger.error(f"Failed searching keyword '{keyword}': {e}")
                continue

            for tweet in tweets:
                scanned_count += 1

                # 1. Deduplication
                if self.repo.is_tweet_processed(tweet.id):
                    continue

                # 2. Virality Momentum Check
                virality_score = calculate_virality_score(tweet)
                if virality_score < self.settings.virality_threshold:
                    # Save low-virality tweet to DB to prevent re-evaluating
                    self.repo.save_processed_tweet(
                        tweet_id=tweet.id,
                        author_handle=tweet.author_handle,
                        tweet_text=tweet.text,
                        virality_score=virality_score,
                        was_published=False
                    )
                    continue

                # 3. Thread Permission & Toxicity Check
                can_reply, thread_reason = self.thread_manager.evaluate_thread_permission(tweet)
                if not can_reply:
                    self.repo.save_processed_tweet(
                        tweet_id=tweet.id,
                        author_handle=tweet.author_handle,
                        tweet_text=tweet.text,
                        virality_score=virality_score,
                        was_published=False
                    )
                    logger.info(f"Skipping tweet {tweet.id}: {thread_reason}")
                    continue

                # 4. Fact Grounding & Verification
                eval_result = self.grounding.evaluate_and_draft(tweet.text, tweet.author_handle)
                if not eval_result.is_worth_replying or not eval_result.draft_reply:
                    self.repo.save_processed_tweet(
                        tweet_id=tweet.id,
                        author_handle=tweet.author_handle,
                        tweet_text=tweet.text,
                        virality_score=virality_score,
                        was_published=False
                    )
                    continue

                # 5. Anti-Bot Humanizer
                final_reply = Humanizer.sanitize(
                    text=eval_result.draft_reply,
                    link=eval_result.recommended_link
                )

                # 6. Publish or Dry-Run
                was_published = False
                publish_info = None

                if self.settings.dry_run:
                    logger.info(f"[DRY RUN] Would reply to @{tweet.author_handle} ({tweet.id}): {final_reply}")
                    was_published = False
                    publish_info = {"mode": "dry_run", "simulated": True}
                else:
                    try:
                        publish_info = self.provider.post_reply(
                            text=final_reply,
                            reply_to_tweet_id=tweet.id
                        )
                        was_published = True
                        replies_sent += 1
                        self.thread_manager.record_interaction(tweet)
                    except Exception as e:
                        logger.error(f"Failed publishing reply to {tweet.id}: {e}")

                # Save record to DB
                self.repo.save_processed_tweet(
                    tweet_id=tweet.id,
                    parent_tweet_id=tweet.in_reply_to_tweet_id,
                    author_handle=tweet.author_handle,
                    tweet_text=tweet.text,
                    reply_generated=final_reply,
                    link_attached=eval_result.recommended_link,
                    virality_score=virality_score,
                    was_published=was_published
                )

                results.append({
                    "tweet_id": tweet.id,
                    "author": tweet.author_handle,
                    "virality_score": virality_score,
                    "claim": eval_result.claim_identified,
                    "reply": final_reply,
                    "published": was_published
                })

                # If quota reached during cycle, stop
                if (current_monthly_count + replies_sent) >= self.settings.monthly_max_replies:
                    break

        # Log run
        status = "SUCCESS" if replies_sent > 0 or self.settings.dry_run else "IDLE"
        self.repo.log_run(
            tweets_scanned=scanned_count,
            replies_sent=replies_sent,
            status=status
        )

        return {
            "status": status,
            "scanned": scanned_count,
            "replies_sent": replies_sent,
            "results": results
        }
