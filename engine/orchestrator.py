"""Main Orchestrator pipeline connecting all zioX modules."""

import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from config.settings import Settings
from database.repository import Repository
from providers.base import BaseTwitterProvider, Tweet
from engine.virality import calculate_virality_score, is_viral_candidate, get_virality_tier
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

    def run_cycle(self, interactive: bool = False) -> Dict[str, Any]:
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

        # 1. Ingestion across all keywords with deduplication
        candidate_tweets: Dict[str, Tweet] = {}
        for keyword in self.settings.search_keywords:
            try:
                tweets = self.provider.search_recent_tweets(keyword, limit=5)
                for tweet in tweets:
                    if tweet.id not in candidate_tweets and not self.repo.is_tweet_processed(tweet.id):
                        candidate_tweets[tweet.id] = tweet
            except Exception as e:
                logger.error(f"Failed searching keyword '{keyword}': {e}")
                continue

        # 2. Sort candidate tweets by virality velocity (highest momentum first)
        sorted_tweets = sorted(
            candidate_tweets.values(),
            key=lambda t: calculate_virality_score(t),
            reverse=True
        )

        for tweet in sorted_tweets:
            scanned_count += 1
            virality_score = calculate_virality_score(tweet)

            # Virality Momentum Check
            if virality_score < self.settings.virality_threshold:
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

            # Interactive Human-in-the-Loop review
            if interactive:
                tier = get_virality_tier(tweet)
                print("\n" + "=" * 65)
                print("           [HUMAN-IN-THE-LOOP INTERACTIVE REVIEW]")
                print("=" * 65)
                print(f" Target User  : @{tweet.author_handle} (Tweet ID: {tweet.id})")
                print(f" Content      : \"{tweet.text}\"")
                print(f" Virality     : Score {virality_score} [{tier}]")
                print(f" Claim Flagged: {eval_result.claim_identified}")
                if eval_result.verified_facts:
                    print(f" Facts Cited  : {' | '.join(eval_result.verified_facts)}")
                print(f" Draft Reply  : {final_reply}")
                print("-" * 65)
                print(" Action choices: [A]pprove & Send | [E]dit Draft | [S]kip Tweet | [Q]uit Cycle")
                try:
                    choice = input(" Your choice [A/E/S/Q] (Default: A) > ").strip().lower()
                except (EOFError, KeyboardInterrupt):
                    choice = "q"

                if choice == "q":
                    print("[zioX] Interactive cycle terminated by user.")
                    break
                elif choice == "s":
                    print(f"[zioX] Tweet {tweet.id} skipped per user instruction.")
                    self.repo.save_processed_tweet(
                        tweet_id=tweet.id,
                        author_handle=tweet.author_handle,
                        tweet_text=tweet.text,
                        virality_score=virality_score,
                        was_published=False
                    )
                    continue
                elif choice == "e":
                    try:
                        edited_text = input(" Enter your revised text > ").strip()
                    except (EOFError, KeyboardInterrupt):
                        edited_text = ""
                    if edited_text:
                        final_reply = Humanizer.sanitize(
                            text=edited_text,
                            link=eval_result.recommended_link
                        )
                        print(f" [Updated Reply]: {final_reply}")

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

    def process_queue(
        self,
        interactive: bool = False,
        limit: int = 10,
        target_tweet_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Processes candidate tweets waiting in the DISCOVERED queue.
        Evaluates virality, checks thread permissions, runs Gemini grounding,
        prompts in interactive mode (if enabled), and publishes the verified reply.
        """
        current_monthly_count = self.repo.get_monthly_reply_count()
        if current_monthly_count >= self.settings.monthly_max_replies:
            msg = f"Monthly reply ceiling reached ({current_monthly_count}/{self.settings.monthly_max_replies}). Process aborted."
            logger.warning(msg)
            return {"status": "QUOTA_EXCEEDED", "processed": 0, "replies_sent": 0, "details": msg}

        # 1. Fetch items from queue or specific ID
        pending_items = []
        if target_tweet_id:
            with self.repo._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM processed_tweets WHERE tweet_id = ?", (target_tweet_id,))
                row = cursor.fetchone()
                if row:
                    pending_items = [dict(row)]
                else:
                    live_t = self.provider.get_tweet(target_tweet_id)
                    if live_t:
                        pending_items = [{
                            "tweet_id": live_t.id,
                            "author_handle": live_t.author_handle,
                            "tweet_text": live_t.text,
                            "virality_score": calculate_virality_score(live_t),
                            "parent_tweet_id": live_t.in_reply_to_tweet_id,
                            "status": "DISCOVERED"
                        }]
        else:
            pending_items = self.repo.get_pending_tweets(limit=limit)

        if not pending_items:
            logger.info("No candidate tweets found in queue.")
            return {"status": "EMPTY_QUEUE", "processed": 0, "replies_sent": 0, "results": []}

        processed_count = 0
        replies_sent = 0
        results: List[Dict[str, Any]] = []

        for item in pending_items:
            tweet_id = item["tweet_id"]
            author = item.get("author_handle", "unknown")
            text = item.get("tweet_text", "")
            score = float(item.get("virality_score", 0.0))
            parent_id = item.get("parent_tweet_id")

            # If text is empty or author is unknown, fetch live from X
            if not text or author == "unknown":
                live_tweet = self.provider.get_tweet(tweet_id)
                if live_tweet:
                    text = live_tweet.text
                    author = live_tweet.author_handle
                    score = calculate_virality_score(live_tweet)
                    parent_id = live_tweet.in_reply_to_tweet_id
                else:
                    logger.warning(f"Could not retrieve tweet text for {tweet_id}. Skipping.")
                    self.repo.update_tweet_status(tweet_id, status="SKIPPED")
                    continue

            processed_count += 1
            tweet_obj = Tweet(
                id=tweet_id,
                text=text,
                author_handle=author,
                created_at=datetime.now(timezone.utc),
                conversation_id=tweet_id,
                in_reply_to_tweet_id=parent_id
            )

            # 2. Thread Permission & Toxicity Check
            can_reply, thread_reason = self.thread_manager.evaluate_thread_permission(tweet_obj)
            if not can_reply:
                self.repo.update_tweet_status(tweet_id, status="SKIPPED")
                logger.info(f"Skipping queued tweet {tweet_id}: {thread_reason}")
                continue

            # 3. Fact Grounding & Verification
            eval_result = self.grounding.evaluate_and_draft(text, author)
            if not eval_result.is_worth_replying or not eval_result.draft_reply:
                self.repo.update_tweet_status(tweet_id, status="SKIPPED")
                logger.info(f"Tweet {tweet_id} not worth replying (factual claim missing or unsupported).")
                continue

            # 4. Anti-Bot Humanizer
            final_reply = Humanizer.sanitize(
                text=eval_result.draft_reply,
                link=eval_result.recommended_link
            )

            # 5. Interactive Human-in-the-Loop review
            if interactive:
                tier = get_virality_tier(tweet_obj)
                print("\n" + "=" * 65)
                print("           [HUMAN-IN-THE-LOOP INTERACTIVE REVIEW]")
                print("=" * 65)
                print(f" Target User  : @{author} (Tweet ID: {tweet_id})")
                print(f" Content      : \"{text}\"")
                print(f" Virality     : Score {score} [{tier}]")
                print(f" Claim Flagged: {eval_result.claim_identified}")
                if eval_result.verified_facts:
                    print(f" Facts Cited  : {' | '.join(eval_result.verified_facts)}")
                print(f" Draft Reply  : {final_reply}")
                print("-" * 65)
                print(" Action choices: [A]pprove & Send | [E]dit Draft | [S]kip Tweet | [Q]uit Cycle")
                try:
                    choice = input(" Your choice [A/E/S/Q] (Default: A) > ").strip().lower()
                except (EOFError, KeyboardInterrupt):
                    choice = "q"

                if choice == "q":
                    print("[zioX] Interactive cycle terminated by user.")
                    break
                elif choice == "s":
                    print(f"[zioX] Tweet {tweet_id} skipped per user instruction.")
                    self.repo.update_tweet_status(tweet_id, status="SKIPPED")
                    continue
                elif choice == "e":
                    try:
                        edited_text = input(" Enter your revised text > ").strip()
                    except (EOFError, KeyboardInterrupt):
                        edited_text = ""
                    if edited_text:
                        final_reply = Humanizer.sanitize(
                            text=edited_text,
                            link=eval_result.recommended_link
                        )
                        print(f" [Updated Reply]: {final_reply}")

            # 6. Publish or Dry-Run
            was_published = False
            if self.settings.dry_run:
                logger.info(f"[DRY RUN] Would reply to @{author} ({tweet_id}): {final_reply}")
                was_published = False
                self.repo.update_tweet_status(
                    tweet_id=tweet_id,
                    status="PROCESSED_DRY_RUN",
                    reply_generated=final_reply,
                    link_attached=eval_result.recommended_link,
                    was_published=False
                )
            else:
                try:
                    self.provider.post_reply(
                        text=final_reply,
                        reply_to_tweet_id=tweet_id
                    )
                    was_published = True
                    replies_sent += 1
                    self.thread_manager.record_interaction(tweet_obj)
                    self.repo.update_tweet_status(
                        tweet_id=tweet_id,
                        status="PUBLISHED",
                        reply_generated=final_reply,
                        link_attached=eval_result.recommended_link,
                        was_published=True
                    )
                except Exception as e:
                    logger.error(f"Failed publishing reply to {tweet_id}: {e}")
                    self.repo.update_tweet_status(tweet_id, status="FAILED")
                    continue

            results.append({
                "tweet_id": tweet_id,
                "author": author,
                "virality_score": score,
                "claim": eval_result.claim_identified,
                "reply": final_reply,
                "published": was_published
            })

            if (current_monthly_count + replies_sent) >= self.settings.monthly_max_replies:
                break

        status = "SUCCESS" if replies_sent > 0 or self.settings.dry_run else "IDLE"
        self.repo.log_run(
            tweets_scanned=processed_count,
            replies_sent=replies_sent,
            status=status
        )

        return {
            "status": status,
            "processed": processed_count,
            "replies_sent": replies_sent,
            "results": results
        }
