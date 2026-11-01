# Proposal

## Why

While `zioX` already supports multi-subscriber onboarding and unique variation routing, its current pipeline is constrained to at most 4 variations per tweet, 2 tweets per cycle, single-pass `getUpdates` polling, and N+1 database queries per subscriber—meaning that scaling from 5 to 1,000 subscribers leaves the vast majority of registered users without actionable messages. Furthermore, dispatching cards to inactive "ghost" subscribers wastes AI tokens and variation slots unless the system verifies subscriber readiness and tracks engagement before continuing to route posts to them.

## What Changes

- **Phase 1 — Scalable Multi-Cohort Sharding & Batch Variation Engine (`engine/grounding.py`, `engine/humanizer.py`, `engine/orchestrator.py`, `config/settings.py`)**:
  - Upgrade `GroundingEngine` with batch multi-variation generation (`generate_variations_batch`) capable of producing 10+ distinct reply variations per Gemini call and chaining batches with excluded angles when larger cohorts (e.g., 20–50 subscribers per viral post wave) are needed.
  - Upgrade `Humanizer.diversify_links_for_variations` to enforce a configurable link-to-no-link mix (`no_link_variation_ratio`, e.g., 40% linkless replies and 60% diversified proof links) so large cohorts replying to the same viral post avoid X's coordinated link-spam filters and benefit from higher organic reach on linkless replies.
  - Decouple Telegram community distribution limits (`telegram_tweets_per_cycle`, `target_cohort_size_per_tweet`) from single-account direct publishing caps (`max_replies_per_cycle`), distributing 5 to 1,000+ active subscribers horizontally across multiple viral posts in sharded cohorts and supporting multi-wave dispatches while posts remain active.
- **Phase 2 — Single-Query Eligibility SQL, Language Filtering & Quota Commands (`database/schema.py`, `database/repository.py`, `engine/telegram_dispatcher.py`)**:
  - Eliminate the N+1 database query bottleneck (which previously issued 2,000 queries per tweet at 1,000 subscribers) by introducing a single consolidated SQL query (`get_eligible_subscribers_for_tweet`) that filters by `active = 1`, readiness/engagement verification status, language match (`preferred_lang`), daily quota (`daily_count < effective_daily_limit`), and non-duplicate `tweet_id` in one round-trip.
  - Add per-subscriber language preferences (`preferred_lang` column: `en`, `ar`, `both`, manageable via `/lang <en|ar|both>`) so subscribers only receive viral posts in languages they can read and reply to.
  - Add `/limit <number>` and `/quota` Telegram commands allowing subscribers to inspect their quota and adjust their personal daily target up to the centrally managed ceiling (`max_user_daily_limit` per tier).
- **Phase 3 — Subscriber Readiness Verification & Engagement Tracking (`database/schema.py`, `database/repository.py`, `engine/telegram_dispatcher.py`)**:
  - **Pre-Activation Readiness Gate**: New subscribers who send `/start` enter a `pending_confirmation` state (`ready_confirmed = 0`) and receive an interactive readiness prompt with an inline callback button (`✅ אני מוכן להגיב` / `/ready`) before receiving live viral post dispatches.
  - **Action Tracking & Auto-Pause ("Ghost" Prevention)**: Add an inline confirmation button (`✅ הגבתי ב-X` / callback `ack:<tweet_id>`) alongside the X Web Intent button on every dispatched review card, plus `consecutive_unconfirmed` tracking on `subscribers`. If a subscriber receives `max_unconfirmed_dispatches` (e.g., 5) cards in a row without confirming action, the system automatically pauses their feed (`active = 0`) and sends a one-tap wake-up prompt (`🔔 חזרתי - שלח לי פוסטים` / `/ready`) so AI tokens and unique variations are reserved exclusively for active responders.
  - **High-Throughput Telegram Delivery**: Add paginated `getUpdates` loops (handling 100+ new commands/callbacks per cycle), automatic deactivation on `HTTP 403 Forbidden` (bot blocked by user), and rate-limited batch dispatching respecting Telegram's 30 msgs/sec ceiling.

## Ban Risk Assessment & Hosting/Service Cost Implications

- **X Account Ban Risk Assessment**:
  - **End-User Accounts (Minimal Coordinated Spam Risk)**: Horizontal cohort sharding (`target_cohort_size_per_tweet`) spreads 1,000 subscribers across multiple viral threads rather than dumping all 1,000 onto a single post simultaneously. Combining 100% unique text hashes with a 40% linkless / 60% diversified-link ratio ensures replies look completely organic to X's Coordinated Inauthentic Behavior (CIB) heuristics.
  - **Central Scanner Account (Unchanged Low Footprint)**: Separating `telegram_tweets_per_cycle` from `max_replies_per_cycle` utilizes tweets already discovered in the single Boolean `OR` scan without adding extra X search calls.
- **Hosting & Service Cost Implications (\$0.00/month Baseline)**:
  - **Database (Turso Free Tier)**: Replacing 2,000 N+1 queries per tweet with 1 consolidated SQL query reduces Turso row reads/requests by >99%, keeping 1,000 subscribers well within Turso's free tier.
  - **AI Token Efficiency (Zero Waste on Inactive Users)**: The pre-activation readiness gate (`/ready` / inline button) and automatic pause after `max_unconfirmed_dispatches` ensure Gemini tokens are only spent on verified, responsive community members.

## Capabilities

### New Capabilities

### Modified Capabilities
- `storage-turso`: Add schema migrations and repository methods for subscriber language preferences (`preferred_lang`), engagement/readiness tracking (`ready_confirmed`, `consecutive_unconfirmed`, `confirmed_at` on `dispatches`), and single-query cohort eligibility selection (`get_eligible_subscribers_for_tweet`).
- `gemini-grounding`: Add batch variation generation (`generate_variations_batch`) supporting configurable batch sizes (`max_variations_per_gemini_call`) and multi-batch angle exclusion for large subscriber cohorts.
- `humanizer-stealth`: Add configurable linkless variation ratio (`no_link_variation_ratio`) to `diversify_links_for_variations` so cohorts mix link-backed and pure-text replies.
- `telegram-dispatcher`: Add paginated `getUpdates` processing (messages + `callback_query`), `/lang`, `/limit`, `/quota`, and `/ready` commands, pre-activation readiness confirmation, inline action-confirmation callbacks (`ack:<tweet_id>`), auto-pause on unconfirmed streak, and `HTTP 403` auto-deactivation.
- `pipeline-scheduler`: Add horizontal cohort sharding across queued tweets, multi-wave campaign dispatching, and language-aware routing in `BotOrchestrator`.

## Impact

- **Configuration (`config/settings.py`)**: Add `target_cohort_size_per_tweet: int = 25`, `max_variations_per_gemini_call: int = 10`, `telegram_tweets_per_cycle: int = 10`, `no_link_variation_ratio: float = 0.4`, `max_user_daily_limit: int = 5`, and `max_unconfirmed_dispatches: int = 5`.
- **Database (`database/schema.py`, `database/repository.py`)**: Migrate `subscribers` (`preferred_lang`, `ready_confirmed`, `consecutive_unconfirmed`, `total_confirmed_replies`) and `dispatches` (`confirmed`, `confirmed_at`); add `get_eligible_subscribers_for_tweet()`, `confirm_subscriber_ready()`, `confirm_dispatch_replied()`, `update_subscriber_language()`, and `update_subscriber_daily_limit()`.
- **AI & Humanizer (`engine/grounding.py`, `engine/humanizer.py`)**: Add `generate_variations_batch()` and `no_link_variation_ratio` support.
- **Telegram & Orchestrator (`engine/telegram_dispatcher.py`, `engine/orchestrator.py`)**: Upgrade onboarding/callback state machine, language-matched horizontal sharding, and multi-wave queue lifecycle.
