# Design

## Context

See `proposal.md` for full motivation. Currently, `zioX` operates as a single-operator pipeline:
1. `DiscoveryRadar.scan_keywords()` in `engine/radar.py` loops through all 9 `search_keywords` one by one with a static `time.sleep(1.2)`, issuing 9 separate GraphQL search calls to X per cycle through `TwikitTwitterProvider`. If X returns an authentication challenge (`401`/`403`) or rate limit (`429`), `TwikitTwitterProvider.search_recent_tweets()` catches the exception, logs it, and returns `[]`, causing `DiscoveryRadar` to continue firing the remaining search queries against a flagged session.
2. `GroundingEngine.evaluate_and_draft()` in `engine/grounding.py` returns a single `draft_reply` string per tweet.
3. `TelegramDispatcher.dispatch_review()` in `engine/telegram_dispatcher.py` sends the exact same `draft_reply` to every comma-separated ID in `TELEGRAM_CHAT_ID`, and there is no automatic `/start` onboarding or per-user dispatch tracking.

## Goals / Non-Goals

**Goals:**
- **Phase A (Scanner Safety Shield)**: Cut X search API calls by ~80% via script-grouped Boolean `OR` query consolidation, replace static `1.2s` sleeps with Gaussian jitter, and implement an immediate Circuit Breaker with cooldown persistence (`bot_state`) and Telegram admin alerts when X signals account risk (`401`/`403`/`429`/Lock).
- **Phase B (Multi-Variation AI Engine)**: Generate $N$ distinct, natural-sounding reply variations per viral tweet in a single Gemini call (varying persona/style and attached whitelisted proof links) while maintaining 100% backward compatibility with `FactCheckResult.draft_reply`.
- **Phase C (Zero-Server Telegram Community SaaS)**: Onboard users automatically via Telegram `getUpdates` (`/start`, `/stop`, `/style`), store subscribers and tier quotas (`free` vs. `pro`) in Turso/SQLite, and shard unique variations across subscribers via a `dispatches` ledger so no two users ever post identical text.

**Non-Goals:**
- Hosting a 24/7 web server or FastAPI webhook listener (all Telegram onboarding and dispatching must remain 100% compatible with scheduled cron runs on GitHub Actions).
- Automating direct replies from subscribers' X accounts (subscribers always post via one-tap X Web Intent links to keep 0% ban risk on personal accounts).
- Building external payment checkout webhooks in this change (tier columns `tier` and `daily_limit` will be ready in `subscribers` and manageable via CLI/DB so payment links or Telegram Stars can be toggled without schema changes).

## Decisions

### Decision 1: Script-Aware Boolean `OR` Query Consolidation (`engine/radar.py`)
- **Choice**: Add `DiscoveryRadar.build_consolidated_queries(keywords, max_per_query=5)` that separates Arabic keywords (containing Unicode `\u0600`–`\u06FF`) from English/Latin keywords, wraps multi-word phrases in double quotes (e.g., `"Middle East"`), and joins up to `max_per_query` terms with ` OR ` inside parentheses: `("Israel" OR "Gaza" OR "IDF" OR "Zionism" OR "Hostages")`.
- **Rationale**: X's GraphQL search endpoint supports standard Boolean `OR` syntax and returns mixed results across terms in a single HTTP request. Grouping by script ensures language-coherent top tweets and reduces 9 requests down to 2 requests (~78% reduction).
- **Alternatives Considered**: Combining English and Arabic into one mega-query (rejected because X's `Top` search product skews heavily toward one language when scripts are mixed).

### Decision 2: Exception Classification & Persistent Cooldown Circuit Breaker (`providers/twikit_provider.py`, `engine/radar.py`, `database/repository.py`)
- **Choice**:
  - Introduce a dedicated `ScannerCircuitBreakerError(Exception)` raised by `TwikitTwitterProvider` when an exception message or HTTP status matches rate-limit (`429`, `RateLimit`), auth/session invalidation (`401`, `403`, `Unauthorized`, `Forbidden`, `Could not authenticate you`), or account lock/challenge (`326`, `AccountLocked`, `arkose`).
  - When `DiscoveryRadar.scan_keywords()` catches `ScannerCircuitBreakerError`, it immediately aborts the keyword loop, writes `scanner_cooldown_until` (e.g., current UTC + `scanner_cooldown_minutes`) into the `bot_state` table, and invokes an optional `on_circuit_breaker` callback (wired to `TelegramDispatcher.send_admin_alert`).
- **Rationale**: Prevents a compromised or rate-limited scout session from hammering X 8 more times in the same run or on subsequent cron runs while in quarantine.

### Decision 3: Single-Call Multi-Variation Schema (`engine/grounding.py`, `engine/humanizer.py`)
- **Choice**:
  - Add `DraftVariation(BaseModel)` with fields `style: str` (`factual`, `sharp`, `historical_legal`, `rhetorical_question`), `text: str`, and `recommended_link: Optional[str] = None`.
  - Add `draft_variations: List[DraftVariation] = Field(default_factory=list)` to `FactCheckResult`.
  - Update `SYSTEM_PROMPT` to instruct Gemini to output both `draft_reply` (primary rebuttal) and `draft_variations` (up to `variations_per_tweet` distinct rebuttals, each strictly under 220 characters and using distinct rhetorical angles).
  - **Strict No-Inline-URL Rule**: Explicitly instruct Gemini in `SYSTEM_PROMPT` NOT to embed raw `http://` or `https://` URLs inside `draft_reply` or `DraftVariation.text` (returning links only in `recommended_link`), and have `Humanizer` strip any accidental inline URL before appending the single whitelisted proof link so a reply never ends up with two links.
  - Add `Humanizer.diversify_links_for_variations(variations, tweet_text)` so that if 4 variations are produced for a topic (e.g. `aid` or `legal`), different URLs from matching categories in `whitelisted_sources.json` are attached across variations.
- **Rationale**: Requesting 4 short variations in a single Gemini call uses virtually the same input tokens and latency as 1 variation while guaranteeing semantic diversity across community members and preserving a clean 220-char text + 1 link budget under X's 280-char ceiling.

### Decision 4: Serverless Telegram Onboarding, Confirmation Feedback & Admin-Only Alerting (`database/schema.py`, `engine/telegram_dispatcher.py`, `engine/orchestrator.py`)
- **Choice**:
  - Add 3 new tables in `database/schema.py`:
    1. `subscribers`: `chat_id TEXT UNIQUE NOT NULL`, `username TEXT`, `tier TEXT DEFAULT 'free'`, `daily_limit INTEGER DEFAULT 3`, `preferred_style TEXT DEFAULT 'any'`, `active BOOLEAN DEFAULT 1`, `created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP`.
    2. `dispatches`: `id INTEGER PRIMARY KEY AUTOINCREMENT`, `tweet_id TEXT NOT NULL`, `chat_id TEXT NOT NULL`, `variation_hash TEXT NOT NULL`, `style TEXT`, `dispatched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP`, `UNIQUE(tweet_id, chat_id)`.
    3. `bot_state`: `key TEXT PRIMARY KEY`, `value TEXT NOT NULL`, `updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP`.
  - Seed any static `TELEGRAM_CHAT_ID` entries from `.env` into `subscribers` (with `tier='admin'`, `daily_limit=100`) so existing single-user/operator setups work out of the box without requiring `/start`.
  - Poll `https://api.telegram.org/bot<TOKEN>/getUpdates?offset=<last_update_id + 1>` at the start of each run to process `/start`, `/stop`, and `/style <factual|sharp|historical_legal|rhetorical_question|any>`, storing the updated offset in `bot_state`.
  - **Immediate Confirmation Messages**: When `sync_subscribers()` processes `/start` or `/style`, it immediately sends a confirmation message to that user's `chat_id` (e.g., welcoming them to `zioX` and explaining `/style`, or confirming their updated style preference) so the user receives clear feedback that the bot is active.
  - **Admin-Only Technical Alerts (`send_admin_alert`)**: Technical alerts (such as X Scanner Circuit Breaker HTTP 429/403 cooldown warnings) are dispatched **exclusively** to the operator's `self.chat_ids` (`TELEGRAM_CHAT_ID` from `.env`) and any subscriber with `tier='admin'`—never to regular `free` or `pro` subscribers.

## Risks / Trade-offs

- **[Risk] More active subscribers than generated variations for a single tweet** → **Mitigation**: Each viral tweet is capped at `len(draft_variations)` dispatches per cycle (e.g., 4–5 subscribers per viral tweet), and the next viral tweet in the queue is routed to the next batch of subscribers ordered by least-recently-dispatched (`Round-Robin Sharding`). This naturally limits how many community members pile onto a single tweet while maximizing coverage across multiple viral posts.
- **[Risk] Telegram `getUpdates` only retains unacknowledged updates for 24 hours** → **Mitigation**: Since GitHub Actions runs every 4 hours (`0 */4 * * *`), `getUpdates` is polled 6 times per day, well within Telegram's 24-hour retention window.

## Migration Plan

1. **Database Auto-Migration**: `Repository._init_db()` runs `CREATE TABLE IF NOT EXISTS` for `subscribers`, `dispatches`, and `bot_state` on both local SQLite and remote Turso Cloud SQLite. Zero manual SQL migration is required.
2. **Backward Compatibility**: All existing CLI flags (`--status`, `--radar`, `--process-queue`, `--pipeline`) and existing 20+ unit tests remain 100% compatible because `FactCheckResult.draft_reply` and static `TELEGRAM_CHAT_ID` fallback are preserved.
