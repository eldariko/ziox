"""Main Orchestrator pipeline connecting all zioX modules."""

import inspect
import logging
import math
import random
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple, Set
from config.settings import Settings
from database.repository import Repository
from providers.base import (
    BaseTwitterProvider,
    Tweet,
    ScannerCircuitBreakerError,
    classify_scanner_exception,
)
from engine.virality import calculate_virality_score, is_viral_candidate, get_virality_tier
from engine.thread_state import ThreadManager
from engine.grounding import GroundingEngine, DraftVariation
from engine.humanizer import Humanizer
from engine.radar import DiscoveryRadar
from engine.telegram_dispatcher import TelegramDispatcher

logger = logging.getLogger(__name__)


def calculate_gaussian_jitter(min_delay: float, max_delay: float) -> float:
    """
    Calculate human-like hesitation delay using Gaussian (normal) distribution.
    Bounded strictly between min_delay and max_delay.
    """
    if min_delay >= max_delay:
        return float(min_delay)
    mean = (min_delay + max_delay) / 2.0
    std_dev = (max_delay - min_delay) / 6.0
    delay = random.gauss(mean, std_dev)
    return max(min_delay, min(max_delay, delay))


class BotOrchestrator:
    """Orchestrates tweet ingestion, filtering, fact-checking, and response dispatch."""

    def __init__(
        self,
        settings: Settings,
        repository: Repository,
        provider: BaseTwitterProvider,
        grounding_engine: GroundingEngine,
        telegram_dispatcher: Optional[TelegramDispatcher] = None,
    ):
        self.settings = settings
        self.repo = repository
        self.provider = provider
        self.grounding = grounding_engine
        self.thread_manager = ThreadManager(repository, max_turns=settings.max_thread_turns)
        self.telegram = telegram_dispatcher or TelegramDispatcher(
            bot_token=settings.telegram_bot_token,
            chat_ids=settings.telegram_chat_id
        )

    def _is_scanner_in_cooldown(self) -> Optional[str]:
        """
        Check if the X scanner account is currently in quarantine cooldown (`scanner_cooldown_until` in `bot_state`).
        Returns the ISO timestamp string if still in cooldown, otherwise None.
        """
        cooldown_until_str = self.repo.get_state("scanner_cooldown_until")
        if not cooldown_until_str:
            return None
        try:
            cooldown_dt = datetime.fromisoformat(cooldown_until_str)
            if cooldown_dt.tzinfo is None:
                cooldown_dt = cooldown_dt.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) < cooldown_dt:
                return cooldown_until_str
        except Exception:
            return None
        return None

    def _handle_scanner_circuit_breaker(self, cb_err: ScannerCircuitBreakerError) -> None:
        """
        Record scanner cooldown quarantine in `bot_state` and dispatch an admin-only
        alert via `TelegramDispatcher.send_admin_alert`.
        """
        cooldown_mins = getattr(self.settings, "scanner_cooldown_minutes", 720)
        until_dt = datetime.now(timezone.utc) + timedelta(minutes=cooldown_mins)
        until_iso = until_dt.isoformat()
        self.repo.set_state("scanner_cooldown_until", until_iso)

        alert_msg = (
            f"X Scanner Circuit Breaker triggered ({cb_err.reason}). "
            f"Scanner quarantined until {until_iso} ({cooldown_mins}m cooldown). "
            f"Raw error: {cb_err}"
        )
        logger.critical(f"[CIRCUIT BREAKER QUARANTINE] {alert_msg}")

        if hasattr(self.telegram, "send_admin_alert"):
            try:
                self.telegram.send_admin_alert(alert_text=alert_msg, repository=self.repo)
            except Exception as alert_err:
                logger.error(f"Failed sending admin circuit breaker alert: {alert_err}")

    def _sync_telegram_subscribers_if_enabled(self, interactive: bool) -> None:
        """Poll Telegram `getUpdates` for `/start`, `/ready`, `/stop`, `/style`, `/lang`, `/limit`, `/quota`."""
        if self.settings.telegram_review_enabled and not interactive:
            if hasattr(self.telegram, "sync_subscribers"):
                try:
                    sig = inspect.signature(self.telegram.sync_subscribers)
                    if "max_user_daily_limit" in sig.parameters:
                        self.telegram.sync_subscribers(
                            repository=self.repo,
                            max_user_daily_limit=getattr(self.settings, "max_user_daily_limit", 5),
                        )
                    else:
                        self.telegram.sync_subscribers(repository=self.repo)
                except Exception as sync_err:
                    logger.warning(f"Telegram subscriber sync skipped/failed: {sync_err}")

    @staticmethod
    def detect_tweet_language(text: str) -> str:
        """Return 'ar' if Arabic script characters are present, otherwise 'en'."""
        return "ar" if any("\u0600" <= c <= "\u06ff" for c in (text or "")) else "en"

    def _get_subscriber_demand(self) -> Dict[str, int]:
        """Return current available subscriber demand (`en`, `ar`, `total`)."""
        max_unconfirmed = getattr(self.settings, "max_unconfirmed_dispatches", 5)
        if hasattr(self.repo, "get_available_subscriber_demand"):
            return self.repo.get_available_subscriber_demand(max_unconfirmed=max_unconfirmed)
        active_subs = self.repo.get_active_subscribers()
        return {"en": len(active_subs), "ar": 0, "total": len(active_subs)}

    def _get_dynamic_limit_per_keyword(self, demand_total: Optional[int] = None) -> int:
        """
        Compute dynamic radar `limit_per_keyword` scaled to available subscriber demand:
        - `needed_waves = max(base_cycle_cap, ceil(demand_total / cohort_size))`
        - `dynamic_limit = max(15, min(50, needed_waves * 2))`
        """
        if demand_total is None:
            demand_total = self._get_subscriber_demand().get("total", 0)
        cohort_size = max(1, getattr(self.settings, "target_cohort_size_per_tweet", 25))
        base_cap = getattr(self.settings, "telegram_tweets_per_cycle", 10)
        needed_waves = max(base_cap, math.ceil(demand_total / cohort_size))
        return max(15, min(50, needed_waves * 2))

    def _evaluate_tweet_for_cohort(
        self,
        tweet_id: str,
        tweet_text: str,
        author_handle: str,
        interactive: bool = False,
    ) -> Any:
        """
        Determine how many eligible subscribers need variations for `tweet_id` in the current wave
        and invoke `generate_variations_batch` when a large cohort (>4) is waiting, or standard
        `evaluate_and_draft` for small/single-user runs.
        """
        cohort_cap = getattr(self.settings, "target_cohort_size_per_tweet", 25)
        max_unconfirmed = getattr(self.settings, "max_unconfirmed_dispatches", 5)
        default_vars = getattr(self.settings, "variations_per_tweet", 4)
        max_per_call = getattr(self.settings, "max_variations_per_gemini_call", 10)

        needed_variations = default_vars
        if self.settings.telegram_review_enabled and not interactive and hasattr(self.repo, "get_eligible_subscribers_for_tweet"):
            tweet_lang = self.detect_tweet_language(tweet_text)
            eligible = self.repo.get_eligible_subscribers_for_tweet(
                tweet_id=tweet_id,
                lang=tweet_lang,
                limit=cohort_cap,
                max_unconfirmed=max_unconfirmed,
            )
            if eligible:
                needed_variations = max(default_vars, len(eligible))

        if (
            needed_variations > default_vars
            and hasattr(self.grounding, "generate_variations_batch")
            and callable(getattr(self.grounding, "generate_variations_batch"))
        ):
            res = self.grounding.generate_variations_batch(
                tweet_text=tweet_text,
                author_handle=author_handle,
                total_variations=needed_variations,
                max_per_call=max_per_call,
            )
            # If grounding is a MagicMock without generate_variations_batch configured to return a FactCheckResult,
            # fall back cleanly to evaluate_and_draft
            if hasattr(res, "is_worth_replying") and isinstance(getattr(res, "is_worth_replying"), bool):
                return res

        return self.grounding.evaluate_and_draft(tweet_text, author_handle)

    def _dispatch_to_telegram_community(
        self,
        tweet: Tweet,
        virality_score: float,
        tier: str,
        eval_result: Any,
        final_reply: str,
        effective_link: Optional[str],
    ) -> Tuple[bool, str, int]:
        """
        Dispatch unique variations per eligible subscriber in the current horizontal cohort wave,
        falling back to standard `dispatch_review` for single-chat / legacy mocks.
        Returns `(dispatched_ok, next_tweet_status, sent_count)` where `next_tweet_status` is:
        - `'DISPATCHED_WAVE'` if more eligible subscribers remain for a subsequent wave
        - `'DISPATCHED_TELEGRAM'` if all eligible subscribers have been served
        - `'DISPATCH_FAILED'` if dispatch failed
        """
        cohort_cap = getattr(self.settings, "target_cohort_size_per_tweet", 25)
        max_unconfirmed = getattr(self.settings, "max_unconfirmed_dispatches", 5)
        no_link_ratio = getattr(self.settings, "no_link_variation_ratio", 0.0)

        raw_variations = getattr(eval_result, "draft_variations", None) or []
        if raw_variations:
            # Only apply linkless ratio when we have a community cohort (>3 variations)
            effective_ratio = no_link_ratio if len(raw_variations) >= 4 else 0.0
            diversified_vars = Humanizer.diversify_links_for_variations(
                variations=raw_variations,
                tweet_text=tweet.text,
                validate_links=True,
                max_length=280,
                no_link_variation_ratio=effective_ratio,
            )
        else:
            diversified_vars = [
                {
                    "style": "factual",
                    "text": final_reply,
                    "link": effective_link,
                }
            ]

        active_subs = self.repo.get_active_subscribers()
        if active_subs and hasattr(self.telegram, "dispatch_variations_to_subscribers"):
            sig = inspect.signature(self.telegram.dispatch_variations_to_subscribers)
            call_kwargs: Dict[str, Any] = {
                "repository": self.repo,
                "tweet_id": tweet.id,
                "author_handle": tweet.author_handle,
                "tweet_text": tweet.text,
                "virality_score": virality_score,
                "virality_tier": tier,
                "variations": diversified_vars,
                "claim_flagged": eval_result.claim_identified,
                "verified_facts": eval_result.verified_facts,
            }
            if "cohort_limit" in sig.parameters:
                call_kwargs["cohort_limit"] = cohort_cap
            if "max_unconfirmed" in sig.parameters:
                call_kwargs["max_unconfirmed"] = max_unconfirmed

            sent_count = self.telegram.dispatch_variations_to_subscribers(**call_kwargs)
            if isinstance(sent_count, int) and sent_count > 0:
                # Check if additional eligible subscribers still haven't received this tweet
                tweet_lang = self.detect_tweet_language(tweet.text)
                remaining_eligible = (
                    self.repo.get_eligible_subscribers_for_tweet(
                        tweet_id=tweet.id,
                        lang=tweet_lang,
                        limit=1,
                        max_unconfirmed=max_unconfirmed,
                    )
                    if hasattr(self.repo, "get_eligible_subscribers_for_tweet")
                    else []
                )
                next_status = "DISPATCHED_WAVE" if remaining_eligible else "DISPATCHED_TELEGRAM"
                return True, next_status, sent_count

        # Language-aware fallback: Ensure candidate post language matches recipient before dispatching review
        tweet_lang = self.detect_tweet_language(tweet.text)
        admin_chat_ids = getattr(self.telegram, "chat_ids", [])
        if admin_chat_ids and hasattr(self.repo, "get_subscriber"):
            # Check if any admin recipient matches the candidate tweet language
            has_matching_admin = False
            for cid in admin_chat_ids:
                sub = self.repo.get_subscriber(cid)
                admin_pref = (sub.get("preferred_lang") if sub else "en") or "en"
                if admin_pref in ("both", tweet_lang):
                    has_matching_admin = True
                    break
            if not has_matching_admin:
                logger.warning(
                    f"[DISPATCH FALLBACK SUPPRESSED] Tweet {tweet.id} language ('{tweet_lang}') "
                    f"does not match admin preference. Suppressing fallback dispatch."
                )
                return False, "DISPATCH_SUPPRESSED_LANGUAGE_MISMATCH", 0

        dispatched = bool(
            self.telegram.dispatch_review(
                tweet_id=tweet.id,
                author_handle=tweet.author_handle,
                tweet_text=tweet.text,
                virality_score=virality_score,
                virality_tier=tier,
                draft_reply=final_reply,
                claim_flagged=eval_result.claim_identified,
                verified_facts=eval_result.verified_facts,
            )
        )
        return dispatched, ("DISPATCHED_TELEGRAM" if dispatched else "DISPATCH_FAILED"), (1 if dispatched else 0)

    def _apply_stealth_delay(self, reply_count_in_cycle: int) -> float:
        """
        Apply humanized Gaussian delay before dispatching consecutive replies.
        In dry-run mode or if min_reply_delay_seconds <= 0, skips actual sleeping.
        Returns the delay in seconds.
        """
        if reply_count_in_cycle == 0:
            return 0.0

        delay = calculate_gaussian_jitter(
            self.settings.min_reply_delay_seconds,
            self.settings.max_reply_delay_seconds
        )
        if self.settings.dry_run or self.settings.min_reply_delay_seconds <= 0:
            logger.info(f"[STEALTH PACING] Simulated {delay:.1f}s human hesitation delay (sleep skipped).")
        else:
            logger.info(f"[STEALTH PACING] Applying {delay:.1f}s human hesitation delay to prevent rate limits...")
            time.sleep(delay)
        return delay

    def _resolve_diverse_link(self, proposed_link: Optional[str], text_context: str) -> Optional[str]:
        """
        Check if proposed link or fallback link has been posted recently.
        If recent within cooldown period, suppress link attachment to maintain diversity.
        """
        candidate = proposed_link
        if not candidate:
            candidate = Humanizer.match_whitelisted_link(text_context)

        if candidate and self.repo.is_link_recently_posted(
            candidate,
            cooldown_minutes=self.settings.link_cooldown_minutes,
            include_dry_run=self.settings.dry_run
        ):
            logger.info(
                f"[LINK DIVERSITY] Link '{candidate}' was posted within the last "
                f"{self.settings.link_cooldown_minutes}m. Throttling link to maintain domain diversity."
            )
            return None
        return candidate

    def _get_effective_cycle_cap(self, interactive: bool, demand_total: Optional[int] = None) -> int:
        """
        Return the per-cycle tweet/wave cap:
        - When Telegram community distribution is enabled (non-interactive) and subscribers are active,
          scale dynamically with `ceil(demand_total / target_cohort_size_per_tweet)` so 100% of available
          subscribers can receive at least one post per run.
        - Otherwise use `max_replies_per_cycle`.
        """
        if self.settings.telegram_review_enabled and not interactive:
            active_subs = self.repo.get_active_subscribers()
            if len(active_subs) > 1:
                if demand_total is None:
                    demand_total = self._get_subscriber_demand().get("total", len(active_subs))
                cohort_size = max(1, getattr(self.settings, "target_cohort_size_per_tweet", 25))
                needed_waves = math.ceil(demand_total / cohort_size)
                return max(
                    self.settings.max_replies_per_cycle,
                    getattr(self.settings, "telegram_tweets_per_cycle", 10),
                    needed_waves,
                )
        return self.settings.max_replies_per_cycle

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

        # Sync Telegram subscribers if Telegram review is enabled
        self._sync_telegram_subscribers_if_enabled(interactive=interactive)

        # Check scanner cooldown quarantine
        cooldown_until = self._is_scanner_in_cooldown()
        if cooldown_until:
            msg = f"X Scanner is in cooldown quarantine until {cooldown_until}. Skipping live search."
            logger.warning(msg)
            self.repo.log_run(0, 0, "SKIPPED_SCANNER_COOLDOWN", msg)
            return {"status": "SCANNER_COOLDOWN", "scanned": 0, "replies_sent": 0, "details": msg, "results": []}

        demand = self._get_subscriber_demand()
        dynamic_search_limit = (
            self._get_dynamic_limit_per_keyword(demand["total"])
            if self.settings.telegram_review_enabled and not interactive
            else 5
        )
        max_age_minutes = getattr(self.settings, "max_tweet_age_hours", 24.0) * 60.0

        # 1. Ingestion across search queries with Boolean OR consolidation & circuit breaker protection
        candidate_tweets: Dict[str, Tweet] = {}
        min_faves_val = getattr(self.settings, 'search_min_faves', 0)
        queries_to_run = (
            DiscoveryRadar.build_consolidated_queries(
                self.settings.search_keywords,
                max_per_query=self.settings.max_keywords_per_query,
                min_faves=min_faves_val
            )
            if self.settings.combine_search_queries
            else [f'{k.strip()} min_faves:{min_faves_val}' if min_faves_val > 0 else k.strip() for k in self.settings.search_keywords if k.strip()]
        )

        for idx, query_str in enumerate(queries_to_run):
            if idx > 0:
                delay = calculate_gaussian_jitter(
                    self.settings.min_search_delay_seconds,
                    self.settings.max_search_delay_seconds
                )
                if not self.settings.dry_run and delay > 0:
                    time.sleep(delay)

            try:
                tweets = self.provider.search_recent_tweets(query_str, limit=dynamic_search_limit)
                for tweet in tweets:
                    if tweet.age_in_minutes > max_age_minutes:
                        continue
                    if tweet.id not in candidate_tweets and not self.repo.is_tweet_processed(tweet.id):
                        candidate_tweets[tweet.id] = tweet
            except Exception as e:
                cb_err = classify_scanner_exception(e)
                if cb_err is not None:
                    self._handle_scanner_circuit_breaker(cb_err)
                    self.repo.log_run(
                        len(candidate_tweets),
                        0,
                        f"ABORTED_CIRCUIT_BREAKER_{cb_err.reason}",
                        str(cb_err)
                    )
                    break
                logger.error(f"Failed searching query '{query_str}': {e}")
                continue

        # 2. Sort candidate tweets by virality velocity (highest momentum first)
        sorted_tweets = sorted(
            candidate_tweets.values(),
            key=lambda t: calculate_virality_score(t),
            reverse=True
        )

        cycle_cap = self._get_effective_cycle_cap(interactive=interactive, demand_total=demand["total"])

        for tweet in sorted_tweets:
            # Per-cycle rate limiting cap
            if replies_sent >= cycle_cap:
                logger.info(
                    f"[STEALTH PACING] Reached cycle cap of {cycle_cap} replies. Ending cycle."
                )
                break

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

            # 4. Fact Grounding & Verification (Cohort-Sized Batch Generation)
            eval_result = self._evaluate_tweet_for_cohort(
                tweet_id=tweet.id,
                tweet_text=tweet.text,
                author_handle=tweet.author_handle,
                interactive=interactive,
            )
            if not eval_result.is_worth_replying or not eval_result.draft_reply:
                self.repo.save_processed_tweet(
                    tweet_id=tweet.id,
                    author_handle=tweet.author_handle,
                    tweet_text=tweet.text,
                    virality_score=virality_score,
                    was_published=False
                )
                continue

            # 5. Anti-Bot Humanizer with Link Diversity Check
            effective_link = self._resolve_diverse_link(eval_result.recommended_link, tweet.text)
            final_reply = Humanizer.sanitize(
                text=eval_result.draft_reply,
                link=effective_link,
                auto_attach_whitelist=(effective_link is not None)
            )

            # Interactive Human-in-the-Loop review
            if interactive:
                tier = get_virality_tier(tweet)
                char_count = Humanizer.calculate_tweet_length(final_reply)
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
                print(f" Length       : {char_count}/280 chars{' (OK)' if char_count <= 280 else ' [EXCEEDS LIMIT!]'}")
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
                            link=effective_link,
                            auto_attach_whitelist=(effective_link is not None)
                        )
                        char_count = Humanizer.calculate_tweet_length(final_reply)
                        print(f" [Updated Reply]: {final_reply}")
                        print(f" [New Length]   : {char_count}/280 chars{' (OK)' if char_count <= 280 else ' [EXCEEDS LIMIT!]'}")

            # Ensure final reply does not exceed Twitter 280 limit before dispatching
            final_reply = Humanizer.enforce_length_limit(final_reply, max_length=280)

            # 6. Telegram Review Dispatch (Asynchronous Human-in-the-Loop & Multi-User Sharding)
            if self.settings.telegram_review_enabled and not interactive:
                tier = get_virality_tier(tweet)
                dispatched, next_status, _sent_cnt = self._dispatch_to_telegram_community(
                    tweet=tweet,
                    virality_score=virality_score,
                    tier=tier,
                    eval_result=eval_result,
                    final_reply=final_reply,
                    effective_link=effective_link,
                )

                # Save record to DB (status is DISPATCHED_WAVE if more subscribers remain, else DISPATCHED_TELEGRAM)
                self.repo.save_processed_tweet(
                    tweet_id=tweet.id,
                    parent_tweet_id=tweet.in_reply_to_tweet_id,
                    author_handle=tweet.author_handle,
                    tweet_text=tweet.text,
                    reply_generated=final_reply,
                    link_attached=effective_link,
                    virality_score=virality_score,
                    was_published=False,
                    status=next_status,
                )

                replies_sent += 1
                results.append({
                    "tweet_id": tweet.id,
                    "author": tweet.author_handle,
                    "virality_score": virality_score,
                    "claim": eval_result.claim_identified,
                    "reply": final_reply,
                    "published": False,
                    "telegram_dispatched": dispatched,
                    "status": next_status,
                })

                if replies_sent >= cycle_cap:
                    logger.info(
                        f"[STEALTH PACING] Reached cycle cap of {cycle_cap} replies. Ending cycle."
                    )
                    break
                continue

            # 7. Apply stealth delay before consecutive replies
            self._apply_stealth_delay(replies_sent)

            # 8. Publish or Dry-Run
            was_published = False
            publish_info = None

            if self.settings.dry_run:
                logger.info(f"[DRY RUN] Would reply to @{tweet.author_handle} ({tweet.id}): {final_reply}")
                was_published = False
                publish_info = {"mode": "dry_run", "simulated": True}
                replies_sent += 1
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
                link_attached=effective_link,
                virality_score=virality_score,
                was_published=was_published,
                status="PUBLISHED" if was_published else ("PROCESSED_DRY_RUN" if self.settings.dry_run else "FAILED")
            )

            results.append({
                "tweet_id": tweet.id,
                "author": tweet.author_handle,
                "virality_score": virality_score,
                "claim": eval_result.claim_identified,
                "reply": final_reply,
                "published": was_published,
            })

            # Check cycle cap
            if replies_sent >= cycle_cap:
                logger.info(
                    f"[STEALTH PACING] Reached cycle cap of {cycle_cap} replies. Ending cycle."
                )
                break

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
        target_tweet_id: Optional[str] = None,
        allow_multi_wave_in_run: bool = False,
    ) -> Dict[str, Any]:
        """
        Processes candidate tweets waiting in the DISCOVERED (or DISPATCHED_WAVE) queue.
        Evaluates virality, checks thread permissions, runs Gemini grounding (in cohort batches),
        prompts in interactive mode (if enabled), applies stealth pacing & link diversity,
        and publishes or dispatches the verified reply variations.
        """
        current_monthly_count = self.repo.get_monthly_reply_count()
        if current_monthly_count >= self.settings.monthly_max_replies:
            msg = f"Monthly reply ceiling reached ({current_monthly_count}/{self.settings.monthly_max_replies}). Process aborted."
            logger.warning(msg)
            return {"status": "QUOTA_EXCEEDED", "processed": 0, "replies_sent": 0, "details": msg, "evaluations": [], "results": []}

        self._sync_telegram_subscribers_if_enabled(interactive=interactive)

        demand = self._get_subscriber_demand()
        demand_total = demand.get("total", 0)
        cycle_cap = self._get_effective_cycle_cap(interactive=interactive, demand_total=demand_total)
        fetch_limit = max(limit, cycle_cap) if allow_multi_wave_in_run else limit

        def _fetch_pending() -> List[Dict[str, Any]]:
            if target_tweet_id:
                with self.repo._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT * FROM processed_tweets WHERE tweet_id = ?", (target_tweet_id,))
                    row = cursor.fetchone()
                    if row:
                        return [dict(row)]
                    live_t = self.provider.get_tweet(target_tweet_id)
                    if live_t:
                        return [{
                            "tweet_id": live_t.id,
                            "author_handle": live_t.author_handle,
                            "tweet_text": live_t.text,
                            "virality_score": calculate_virality_score(live_t),
                            "parent_tweet_id": live_t.in_reply_to_tweet_id,
                            "status": "DISCOVERED"
                        }]
                return []
            include_waves = bool(self.settings.telegram_review_enabled and not interactive)
            sig = inspect.signature(self.repo.get_pending_tweets)
            if "include_waves" in sig.parameters:
                return self.repo.get_pending_tweets(limit=fetch_limit, include_waves=include_waves)
            return self.repo.get_pending_tweets(limit=fetch_limit)

        pending_items = _fetch_pending()
        if not pending_items:
            logger.info("No candidate tweets found in queue.")
            return {"status": "EMPTY_QUEUE", "processed": 0, "replies_sent": 0, "evaluations": [], "results": []}

        processed_count = 0
        replies_sent = 0
        total_subscribers_dispatched = 0
        results: List[Dict[str, Any]] = []
        evaluations: List[Dict[str, Any]] = []

        max_passes = max(1, cycle_cap) if (allow_multi_wave_in_run and self.settings.telegram_review_enabled and not interactive) else 1

        for pass_idx in range(max_passes):
            if pass_idx > 0:
                if total_subscribers_dispatched >= demand_total or replies_sent >= cycle_cap:
                    break
                pending_items = _fetch_pending()
                if not pending_items:
                    break

            dispatched_in_this_pass = 0

            for item in pending_items:
                # Per-cycle rate limiting cap
                if replies_sent >= cycle_cap:
                    logger.info(
                        f"[STEALTH PACING] Reached queue cycle cap of {cycle_cap} replies. Halting queue run."
                    )
                    break

                if allow_multi_wave_in_run and pass_idx > 0 and total_subscribers_dispatched >= demand_total:
                    break

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
                        evaluations.append({
                            "tweet_id": tweet_id,
                            "author": author,
                            "virality_score": score,
                            "tier": "Unknown",
                            "decision": "SKIPPED",
                            "reason": "Could not retrieve tweet text from Twitter provider",
                            "claim": None,
                            "facts": [],
                            "link": None,
                            "status": "SKIPPED",
                        })
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

                tier = get_virality_tier(tweet_obj)

                # 2. Thread Permission & Toxicity Check
                can_reply, thread_reason = self.thread_manager.evaluate_thread_permission(tweet_obj)
                if not can_reply:
                    self.repo.update_tweet_status(tweet_id, status="SKIPPED")
                    logger.info(f"Skipping queued tweet {tweet_id}: {thread_reason}")
                    evaluations.append({
                        "tweet_id": tweet_id,
                        "author": author,
                        "virality_score": score,
                        "tier": tier,
                        "decision": "SKIPPED",
                        "reason": thread_reason,
                        "claim": None,
                        "facts": [],
                        "link": None,
                        "status": "SKIPPED",
                    })
                    continue

                # 3. Fact Grounding & Verification (Cohort-Sized Batch Generation)
                eval_result = self._evaluate_tweet_for_cohort(
                    tweet_id=tweet_id,
                    tweet_text=text,
                    author_handle=author,
                    interactive=interactive,
                )
                if not eval_result.is_worth_replying or not eval_result.draft_reply:
                    self.repo.update_tweet_status(tweet_id, status="SKIPPED")
                    logger.info(f"Tweet {tweet_id} not worth replying (factual claim missing or unsupported).")
                    reason = getattr(eval_result, "reasoning", "Factual claim missing or unsupported") or "Factual claim missing or unsupported"
                    evaluations.append({
                        "tweet_id": tweet_id,
                        "author": author,
                        "virality_score": score,
                        "tier": tier,
                        "decision": "SKIPPED",
                        "reason": reason,
                        "claim": eval_result.claim_identified,
                        "facts": eval_result.verified_facts or [],
                        "link": None,
                        "status": "SKIPPED",
                    })
                    continue

                # 4. Anti-Bot Humanizer with Link Diversity Check
                effective_link = self._resolve_diverse_link(eval_result.recommended_link, text)
                final_reply = Humanizer.sanitize(
                    text=eval_result.draft_reply,
                    link=effective_link,
                    auto_attach_whitelist=(effective_link is not None)
                )

                # 5. Interactive Human-in-the-Loop review
                if interactive:
                    char_count = Humanizer.calculate_tweet_length(final_reply)
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
                    print(f" Length       : {char_count}/280 chars{' (OK)' if char_count <= 280 else ' [EXCEEDS LIMIT!]'}")
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
                        evaluations.append({
                            "tweet_id": tweet_id,
                            "author": author,
                            "virality_score": score,
                            "tier": tier,
                            "decision": "SKIPPED",
                            "reason": "Skipped per user instruction in interactive review",
                            "claim": eval_result.claim_identified,
                            "facts": eval_result.verified_facts or [],
                            "link": None,
                            "status": "SKIPPED",
                        })
                        continue
                    elif choice == "e":
                        try:
                            edited_text = input(" Enter your revised text > ").strip()
                        except (EOFError, KeyboardInterrupt):
                            edited_text = ""
                        if edited_text:
                            final_reply = Humanizer.sanitize(
                                text=edited_text,
                                link=effective_link,
                                auto_attach_whitelist=(effective_link is not None)
                            )
                            char_count = Humanizer.calculate_tweet_length(final_reply)
                            print(f" [Updated Reply]: {final_reply}")
                            print(f" [New Length]   : {char_count}/280 chars{' (OK)' if char_count <= 280 else ' [EXCEEDS LIMIT!]'}")

                # Ensure final reply does not exceed Twitter 280 limit before dispatching
                final_reply = Humanizer.enforce_length_limit(final_reply, max_length=280)

                # 6. Telegram Review Dispatch in queue processing
                if self.settings.telegram_review_enabled and not interactive:
                    dispatched, next_status, sent_cnt = self._dispatch_to_telegram_community(
                        tweet=tweet_obj,
                        virality_score=score,
                        tier=tier,
                        eval_result=eval_result,
                        final_reply=final_reply,
                        effective_link=effective_link,
                    )

                    self.repo.update_tweet_status(
                        tweet_id=tweet_id,
                        status=next_status,
                        reply_generated=final_reply,
                        link_attached=effective_link,
                        was_published=False
                    )

                    replies_sent += 1
                    total_subscribers_dispatched += sent_cnt
                    dispatched_in_this_pass += sent_cnt
                    results.append({
                        "tweet_id": tweet_id,
                        "author": author,
                        "virality_score": score,
                        "claim": eval_result.claim_identified,
                        "reply": final_reply,
                        "published": False,
                        "telegram_dispatched": dispatched,
                        "status": next_status,
                        "subscribers_served": sent_cnt,
                    })
                    evaluations.append({
                        "tweet_id": tweet_id,
                        "author": author,
                        "virality_score": score,
                        "tier": tier,
                        "decision": "APPROVED",
                        "reason": None,
                        "claim": eval_result.claim_identified,
                        "facts": eval_result.verified_facts or [],
                        "link": effective_link,
                        "status": next_status,
                        "draft_reply": final_reply,
                    })

                    if replies_sent >= cycle_cap:
                        logger.info(
                            f"[STEALTH PACING] Reached queue cycle cap of {cycle_cap} replies. Halting queue run."
                        )
                        break

                    if (current_monthly_count + replies_sent) >= self.settings.monthly_max_replies:
                        break
                    continue

                # 7. Apply stealth delay before consecutive replies
                self._apply_stealth_delay(replies_sent)

                # 8. Publish or Dry-Run
                was_published = False
                if self.settings.dry_run:
                    logger.info(f"[DRY RUN] Would reply to @{author} ({tweet_id}): {final_reply}")
                    was_published = False
                    replies_sent += 1
                    self.repo.update_tweet_status(
                        tweet_id=tweet_id,
                        status="PROCESSED_DRY_RUN",
                        reply_generated=final_reply,
                        link_attached=effective_link,
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
                            link_attached=effective_link,
                            was_published=True
                        )
                    except Exception as e:
                        logger.error(f"Failed publishing reply to {tweet_id}: {e}")
                        self.repo.update_tweet_status(tweet_id, status="FAILED")
                        evaluations.append({
                            "tweet_id": tweet_id,
                            "author": author,
                            "virality_score": score,
                            "tier": tier,
                            "decision": "APPROVED",
                            "reason": f"Publishing failed: {e}",
                            "claim": eval_result.claim_identified,
                            "facts": eval_result.verified_facts or [],
                            "link": effective_link,
                            "status": "FAILED",
                            "draft_reply": final_reply,
                        })
                        continue

                results.append({
                    "tweet_id": tweet_id,
                    "author": author,
                    "virality_score": score,
                    "claim": eval_result.claim_identified,
                    "reply": final_reply,
                    "published": was_published
                })
                evaluations.append({
                    "tweet_id": tweet_id,
                    "author": author,
                    "virality_score": score,
                    "tier": tier,
                    "decision": "APPROVED",
                    "reason": None,
                    "claim": eval_result.claim_identified,
                    "facts": eval_result.verified_facts or [],
                    "link": effective_link,
                    "status": "PUBLISHED" if was_published else "PROCESSED_DRY_RUN",
                    "draft_reply": final_reply,
                })

                # Check cycle cap
                if replies_sent >= cycle_cap:
                    logger.info(
                        f"[STEALTH PACING] Reached queue cycle cap of {cycle_cap} replies. Halting queue run."
                    )
                    break

                if (current_monthly_count + replies_sent) >= self.settings.monthly_max_replies:
                    break

            if allow_multi_wave_in_run and dispatched_in_this_pass == 0:
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
            "subscribers_served": total_subscribers_dispatched,
            "evaluations": evaluations,
            "results": results
        }

    def run_full_pipeline(
        self,
        radar: Any,
        start_jitter_minutes: Optional[float] = None,
        interactive: bool = False,
        limit_queue: int = 10
    ) -> Dict[str, Any]:
        """
        Executes an end-to-end autonomous pipeline run designed for external schedulers:
        1. Applies optional randomized start jitter delay.
        2. Verifies monthly reply quota ceiling.
        3. Syncs Telegram subscribers (`getUpdates`) and checks scanner cooldown quarantine.
        4. Calculates real-time subscriber demand (`get_available_subscriber_demand`) and scales
           radar `limit_per_keyword` and queue wave caps dynamically.
        5. Runs Discovery Radar to search keywords and enqueue viral posts (up to `max_tweet_age_hours`).
        6. Processes pending queue with multi-wave cohort iteration so 100% of available subscribers
           receive at least one candidate post per run.
        7. Automatically generates and publishes a visual Markdown Execution Summary ($GITHUB_STEP_SUMMARY).
        8. Returns full run execution metrics.
        """
        if hasattr(self.telegram, "clear_last_dispatches"):
            self.telegram.clear_last_dispatches()

        pending_before = self.repo.get_pending_tweets(limit=100) if hasattr(self.repo, "get_pending_tweets") else []

        # 1. Start Jitter Calculation
        max_jitter = self.settings.start_jitter_max_minutes if start_jitter_minutes is None else start_jitter_minutes
        if max_jitter > 0:
            jitter_sec = random.uniform(0.0, max_jitter * 60.0)
            if self.settings.dry_run:
                logger.info(f"[START JITTER] Simulated {jitter_sec:.1f}s start delay (skipped in dry-run).")
            else:
                logger.info(f"[START JITTER] Pausing {jitter_sec:.1f}s before starting pipeline to randomize access cadence...")
                time.sleep(jitter_sec)

        # 2. Check Monthly Quota Hard-Stop
        current_monthly_count = self.repo.get_monthly_reply_count()
        if current_monthly_count >= self.settings.monthly_max_replies:
            msg = f"Monthly reply ceiling reached ({current_monthly_count}/{self.settings.monthly_max_replies}). Pipeline halted."
            logger.warning(msg)
            self.repo.log_run(0, 0, "ABORTED_QUOTA_EXCEEDED", msg)
            report = {
                "status": "QUOTA_EXCEEDED",
                "discovered_count": 0,
                "discovered_tweets": [],
                "processed": 0,
                "replies_sent": 0,
                "subscribers_served": 0,
                "details": msg,
                "results": [],
                "evaluations": [],
                "pending_before_count": len(pending_before),
                "pending_after_count": len(pending_before),
                "pending_after_items": pending_before,
                "dispatches": [],
            }
            try:
                from engine.summary_reporter import SummaryReporter
                SummaryReporter.generate_and_publish(
                    run_report=report,
                    settings=self.settings,
                    repository=self.repo,
                )
            except Exception as e:
                logger.debug(f"Could not publish quota step summary: {e}")
            return report

        # Sync subscribers early
        self._sync_telegram_subscribers_if_enabled(interactive=interactive)

        # Calculate real-time subscriber demand
        demand = self._get_subscriber_demand()
        demand_total = demand.get("total", 0)
        dynamic_limit_per_kw = (
            self._get_dynamic_limit_per_keyword(demand_total)
            if self.settings.telegram_review_enabled and not interactive
            else 5
        )
        max_tweet_age_hours = getattr(self.settings, "max_tweet_age_hours", 24.0)

        # 3. Discovery Radar Ingestion (skipped if scanner is in cooldown quarantine)
        discovered = []
        cooldown_until = self._is_scanner_in_cooldown()
        if cooldown_until:
            logger.warning(
                f"[PIPELINE] X Scanner is in cooldown quarantine until {cooldown_until}. "
                f"Skipping live X search and processing existing queue only."
            )
        else:
            try:
                logger.info(
                    f"[PIPELINE] Running Discovery Radar across {len(self.settings.search_keywords)} keywords "
                    f"(demand={demand_total} subscribers, limit_per_keyword={dynamic_limit_per_kw}, max_age={max_tweet_age_hours}h)..."
                )
                scan_sig = inspect.signature(radar.scan_keywords)
                scan_kwargs: Dict[str, Any] = {
                    "provider": self.provider,
                    "keywords": self.settings.search_keywords,
                    "limit_per_keyword": dynamic_limit_per_kw,
                    "min_virality_score": self.settings.virality_threshold,
                    "combine_queries": self.settings.combine_search_queries,
                    "max_keywords_per_query": self.settings.max_keywords_per_query,
                    "min_search_delay_seconds": self.settings.min_search_delay_seconds,
                    "max_search_delay_seconds": self.settings.max_search_delay_seconds,
                    "dry_run": self.settings.dry_run,
                    "on_circuit_breaker": self._handle_scanner_circuit_breaker,
                    "min_faves": getattr(self.settings, 'search_min_faves', 0),
                }
                if "max_tweet_age_hours" in scan_sig.parameters:
                    scan_kwargs["max_tweet_age_hours"] = max_tweet_age_hours

                discovered = radar.scan_keywords(**scan_kwargs)
                logger.info(f"[PIPELINE] Radar discovered and enqueued {len(discovered)} candidate tweets.")
            except Exception as e:
                err_msg = f"Discovery Radar failed: {e}"
                logger.error(err_msg)
                self.repo.log_run(0, 0, "RADAR_ERROR", err_msg)
                report = {
                    "status": "RADAR_ERROR",
                    "discovered_count": 0,
                    "discovered_tweets": [],
                    "processed": 0,
                    "replies_sent": 0,
                    "subscribers_served": 0,
                    "details": err_msg,
                    "results": [],
                    "evaluations": [],
                    "pending_before_count": len(pending_before),
                    "pending_after_count": len(pending_before),
                    "pending_after_items": pending_before,
                    "dispatches": [],
                }
                try:
                    from engine.summary_reporter import SummaryReporter
                    SummaryReporter.generate_and_publish(
                        run_report=report,
                        settings=self.settings,
                        repository=self.repo,
                    )
                except Exception:
                    pass
                return report

        # 4. Queue Responder Dispatch (with multi-wave iteration enabled for full demand coverage)
        effective_cap = self._get_effective_cycle_cap(interactive=interactive, demand_total=demand_total)
        logger.info(
            f"[PIPELINE] Processing queue (demand={demand_total} available subscribers, max cycle waves: {effective_cap})..."
        )
        queue_report = self.process_queue(
            interactive=interactive,
            limit=max(limit_queue, effective_cap),
            allow_multi_wave_in_run=True,
        )

        pending_after = self.repo.get_pending_tweets(limit=100) if hasattr(self.repo, "get_pending_tweets") else []
        dispatches = self.telegram.get_last_dispatches() if hasattr(self.telegram, "get_last_dispatches") else []

        full_report = {
            "status": queue_report.get("status", "SUCCESS"),
            "discovered_count": len(discovered),
            "discovered_tweets": discovered,
            "processed": queue_report.get("processed", 0),
            "replies_sent": queue_report.get("replies_sent", 0),
            "subscribers_served": queue_report.get("subscribers_served", 0),
            "demand": demand,
            "results": queue_report.get("results", []),
            "evaluations": queue_report.get("evaluations", []),
            "radar_scan_stats": getattr(radar, "last_scan_stats", None),
            "pending_before_count": len(pending_before),
            "pending_after_count": len(pending_after),
            "pending_after_items": pending_after,
            "dispatches": dispatches,
        }

        # Auto-publish GitHub Actions Step Summary if GITHUB_STEP_SUMMARY is configured
        try:
            from engine.summary_reporter import SummaryReporter
            SummaryReporter.generate_and_publish(
                run_report=full_report,
                settings=self.settings,
                repository=self.repo,
            )
        except Exception as summary_err:
            logger.warning(f"Failed generating step summary: {summary_err}")

        return full_report
