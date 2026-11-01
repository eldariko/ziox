# Proposal

## Why

To transition `zioX` from a single-operator developer script into an accessible, zero-friction Community Advocacy SaaS, non-technical supporters need to join simply by tapping `/start` in Telegram and receive unique, personalized reply variations via one-tap X Web Intent buttons—without risking coordinated-spam ("copy-paste") detection on X. Simultaneously, the central X scanner account executing searches via GitHub Actions must be protected from rate limits (`HTTP 429`) and session lockouts (`HTTP 401/403`) by consolidating search queries with Boolean `OR` operators, replacing fixed sleep delays with Gaussian jitter, and enforcing an automatic circuit breaker.

## What Changes

- **Phase A — Scanner Safety Shield & Boolean `OR` Query Consolidation (`engine/radar.py`, `providers/twikit_provider.py`, `config/settings.py`)**:
  - Group search keywords by script/language (English vs. Arabic) into consolidated Boolean `OR` queries (e.g., `("Israel" OR "Gaza" OR "IDF" OR "Zionism")`) so each scan cycle executes 1–2 X search requests instead of 9 separate requests (cutting X network footprint by ~80%).
  - Replace the static `1.2s` inter-query delay in `DiscoveryRadar.scan_keywords` with bounded Gaussian jitter (`min_search_delay_seconds` to `max_search_delay_seconds`).
  - Add scanner exception detection (`401`, `403`, `429`, account lock/challenge) and an automatic Circuit Breaker that halts the remaining scan immediately upon detecting account danger, logs the health event, and dispatches an operator alert to Telegram.
- **Phase B — Multi-Variation AI Drafting (`engine/grounding.py`, `engine/humanizer.py`)**:
  - Upgrade `GroundingEngine.evaluate_and_draft` and `FactCheckResult` to generate an array of distinct reply variations (`draft_variations`) in a **single** Gemini API call, each written from a different rhetorical angle/persona (`factual`, `sharp`, `historical_legal`, `rhetorical_question`) and paired with diversified proof links from `assets/proofs/whitelisted_sources.json`.
  - Maintain backward compatibility with `draft_reply` (populated with the primary variation) so single-user CLI and existing tests continue working seamlessly.
- **Phase C — Zero-Server Telegram Community SaaS (`database/schema.py`, `database/repository.py`, `engine/telegram_dispatcher.py`, `engine/orchestrator.py`)**:
  - Add a `subscribers` table (`chat_id`, `username`, `tier`, `daily_limit`, `preferred_style`, `active`, `joined_at`) and a `dispatches` ledger table (`tweet_id`, `chat_id`, `variation_hash`, `dispatched_at`) to SQLite / Turso Cloud DB.
  - Add serverless subscriber synchronization in `TelegramDispatcher.sync_subscribers()` using Telegram's `getUpdates` endpoint at the beginning of each pipeline run to process `/start`, `/stop`, and `/style` commands without requiring a 24/7 webhook server.
  - Upgrade `BotOrchestrator` to scale variation assignment across active subscribers, enforce per-subscriber daily limits (`free` vs. `pro`/`supporter` tiers), record every delivery in `dispatches` to guarantee zero duplicate replies across users on the same viral post, and skip scanning if no active subscribers or manual targets exist.

## Ban Risk Assessment & Hosting/Service Cost Implications

- **X Account Ban Risk Assessment**:
  - **End-User Accounts (0% Automation Ban Risk)**: Subscribers never share X cookies or API keys; they publish replies manually from their own devices via native X Web Intent links (`https://x.com/intent/tweet?...`). Because each subscriber receives a distinct rhetorical variation and proof link (tracked via `dispatches`), X's Coordinated Inauthentic Behavior (copy-paste spam) filters are never triggered.
  - **Central Scanner ("Scout") Account (~80% Lower Fingerprint)**: Consolidating 9 keyword searches into 1–2 Boolean `OR` queries with Gaussian jitter reduces X GraphQL search calls by ~80% per run. If X ever returns `HTTP 401/403/429`, the Circuit Breaker immediately aborts the cycle and alerts the admin rather than continuing to hammer the endpoint. Operationally, only a dedicated secondary "Scout" account is used in `X_AUTH_TOKEN` / `X_CT0`, keeping the operator's personal X profile 100% isolated.
- **Hosting & Service Cost Implications (\$0.00/month Baseline)**:
  - **Compute**: Runs on GitHub Actions (`ziox_cron.yml`) using serverless `getUpdates` polling—\$0.00/month with zero 24/7 server maintenance.
  - **Database**: Turso Cloud SQLite free tier (500 MB storage, 500M row reads/month) easily supports thousands of subscribers and `dispatches` ledger rows at \$0.00/month.
  - **AI Token Efficiency**: Generating 4–5 reply variations inside a single structured JSON response from `gemini-3.5-flash-lite` / `gemini-2.5-flash` pays the input prompt token cost only once, keeping AI costs within the free tier or pennies per month while supporting future `pro` / community boost tiers.

## Capabilities

### New Capabilities

### Modified Capabilities
- `discovery-radar`: Add requirements for Boolean `OR` query consolidation, Gaussian search jitter between queries, and immediate circuit-breaker abort on X rate-limit or authentication errors.
- `gemini-grounding`: Add requirements for generating multiple distinct reply variations (with distinct personas/styles and diversified proof URLs) in a single structured Gemini evaluation call.
- `storage-turso`: Add schema and repository requirements for the `subscribers` table, `dispatches` per-user delivery ledger, and `bot_state` key-value cursor tracking (e.g., Telegram `last_update_id` and scanner cooldown state).
- `telegram-dispatcher`: Add requirements for serverless `getUpdates` subscriber onboarding (`/start`, `/stop`, `/style`), per-subscriber unique variation routing, and admin health alerts.
- `pipeline-scheduler`: Add requirements for demand-driven multi-subscriber orchestration, per-user daily quota enforcement, and variation sharding across active subscribers.

## Impact

- **Configuration (`config/settings.py`)**: Add `combine_search_queries: bool = True`, `max_keywords_per_query: int = 5`, `min_search_delay_seconds: float = 6.0`, `max_search_delay_seconds: float = 15.0`, `variations_per_tweet: int = 4`, `default_free_daily_limit: int = 3`, and `pro_daily_limit: int = 15`.
- **Database (`database/schema.py`, `database/repository.py`)**: Add `subscribers`, `dispatches`, and `bot_state` tables with automatic migration in Local SQLite and Turso Cloud modes.
- **Providers & Radar (`providers/twikit_provider.py`, `engine/radar.py`)**: Add `ScannerCircuitBreakerError` classification (`401`/`403`/`429`), Boolean `OR` query builder, and Gaussian search pacing.
- **AI Grounding (`engine/grounding.py`, `engine/humanizer.py`)**: Extend `FactCheckResult` with `draft_variations: List[DraftVariation]` and multi-link diversification.
- **Telegram & Orchestrator (`engine/telegram_dispatcher.py`, `engine/orchestrator.py`)**: Add `sync_subscribers()`, unique variation assignment per `chat_id`, and `dispatches` deduplication.
