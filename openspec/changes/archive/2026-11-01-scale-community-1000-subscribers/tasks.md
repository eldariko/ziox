# Tasks

## 1. Phase 1: Database Schema Migration & Single-Query Cohort Eligibility (`storage-turso`)

- [x] 1.1 Update `CREATE_SUBSCRIBERS_TABLE` and `CREATE_DISPATCHES_TABLE` in `database/schema.py` and add automatic idempotent column migrations (`preferred_lang`, `ready_confirmed`, `consecutive_unconfirmed`, `total_confirmed_replies` on `subscribers`; `confirmed`, `confirmed_at` on `dispatches`) in `Repository._init_db()` (`database/repository.py`), verifying with `pytest tests/test_repository.py tests/test_turso_adapter.py`.
- [x] 1.2 Implement `get_eligible_subscribers_for_tweet(tweet_id, lang, limit, max_unconfirmed)`, `update_subscriber_language(chat_id, preferred_lang)`, `update_subscriber_daily_limit(chat_id, daily_limit, max_ceiling)`, `confirm_subscriber_ready(chat_id)`, `confirm_dispatch_replied(tweet_id, chat_id)`, and `pause_unresponsive_subscribers(max_unconfirmed)` in `database/repository.py`, plus multi-wave `DISPATCHED_WAVE` queue support in `get_pending_tweets()`, and verify with unit tests in `tests/test_repository.py`.

## 2. Phase 2: Batch Variation Engine & Link/Linkless Ratio (`gemini-grounding`, `humanizer-stealth`)

- [x] 2.1 Add scaling settings (`target_cohort_size_per_tweet`, `max_variations_per_gemini_call`, `telegram_tweets_per_cycle`, `no_link_variation_ratio`, `max_user_daily_limit`, `max_unconfirmed_dispatches`) to `config/settings.py` and implement `GroundingEngine.generate_variations_batch(tweet_text, author_handle, total_variations)` in `engine/grounding.py` supporting multi-batch angle exclusion for cohorts of 5 to 50+ subscribers, verifying with `pytest tests/test_responder.py`.
- [x] 2.2 Upgrade `Humanizer.diversify_links_for_variations()` in `engine/humanizer.py` to accept `no_link_variation_ratio: float = 0.0` so that the specified proportion of cohort variations are formatted as pure text (`link=None`) while the rest rotate across distinct whitelisted proof URLs, verifying with `pytest tests/test_humanizer.py`.

## 3. Phase 3: Telegram Readiness Gate, Action Confirmation & Commands (`telegram-dispatcher`)

- [x] 3.1 Upgrade `TelegramDispatcher.sync_subscribers()` in `engine/telegram_dispatcher.py` to support paginated `getUpdates` loops, `/lang <en|ar|both>`, `/limit <number>`, `/quota`, and `/ready` commands, plus `callback_query` handling (`ready:confirm` and `ack:<tweet_id>`) and `answerCallbackQuery`, verifying with unit tests in `tests/test_telegram_dispatcher.py`.
- [x] 3.2 Upgrade `TelegramDispatcher.dispatch_review()` and `dispatch_variations_to_subscribers()` in `engine/telegram_dispatcher.py` to include the `✅ הגבתי ב-X` (`ack:<tweet_id>`) inline confirmation button, use `repository.get_eligible_subscribers_for_tweet()` (eliminating N+1 queries), auto-deactivate subscribers on `HTTP 403 Forbidden`, and auto-pause subscribers reaching `max_unconfirmed_dispatches` with a wake-up prompt, verifying with `pytest tests/test_telegram_dispatcher.py`.

## 4. Phase 4: Horizontal Cohort Sharding & Multi-Wave Orchestration (`pipeline-scheduler`)

- [x] 4.1 Upgrade `BotOrchestrator` (`engine/orchestrator.py`) to detect tweet language (`en` vs `ar`), size variation batches dynamically via `generate_variations_batch` according to eligible cohort size (`target_cohort_size_per_tweet`), apply `no_link_variation_ratio`, separate `telegram_tweets_per_cycle` from `max_replies_per_cycle`, and transition partially-dispatched viral tweets to `DISPATCHED_WAVE` when additional active subscribers remain, verifying with full regression and scale tests in `pytest tests/test_e2e_pipeline.py`.
