# Proposal

## Why

Currently, zioX suffers from three limitations when scaling to a community of up to 1,000+ active subscribers:
1. **Harsh Linear Age Decay & Narrow `Latest`-Only Search**: The virality formula (`weighted_engagements / (age_in_minutes + 10)`) harshly penalizes high-impact viral posts that are 10 to 24 hours old (requiring 3,350+ weighted points at 11 hours just to pass a 5.0 threshold), while `TwikitTwitterProvider.search_recent_tweets` only queries `product="Latest"` with `limit=5` unless `Latest` returns empty, missing proven viral posts in X's `Top` tab.
2. **Static Scan & Wave Caps Disconnected from Subscriber Demand**: The radar and orchestrator use fixed constants (`limit_per_keyword=5`, `telegram_tweets_per_cycle=10`, `target_cohort_size_per_tweet=25`), capping each run at 250 subscribers and failing to ensure that 100% of available, ready subscribers receive at least one post per run when the community grows to 500–1,000+ users.
3. **Always-On Polling Daemon vs. GitHub Actions Quota**: Running `--poll-telegram` continuously inside GitHub Actions would exhaust the 2,000 free monthly minutes, while periodic batch polling introduces latency when users click interactive Telegram menu buttons (`/start`, `/style`, `/lang`, `/limit`, `/quota`, `/ready`, `ack:<tweet_id>`). Deploying a zero-cost Serverless Cloudflare Worker Webhook connected directly to Turso Cloud HTTP API (`setWebhook`) provides instant (<100ms) 24/7 interactive chat responses without consuming a single GitHub Actions minute.

## What Changes

- **Hybrid Virality Scoring for 1–24h Viral Posts (`engine/virality.py`)**:
  - Upgrade `calculate_virality_score` so that sustained viral posts up to 24 hours old (1,440 minutes) with high absolute engagement are not discarded by linear minute decay, using a hybrid calculation that takes the maximum of instantaneous velocity and an age-damped sustained virality score (or engagement floor boost for posts within 24h).
- **Combined `Top` + `Latest` Search & Age Window Filtering (`providers/twikit_provider.py`, `engine/radar.py`)**:
  - Update `TwikitTwitterProvider.search_recent_tweets` to fetch from both `product="Top"` (capturing viral posts from the last 1–24 hours) and `product="Latest"` (capturing breaking posts), deduplicating by tweet ID and filtering out stale posts older than `max_tweet_age_hours` (default `24` hours).
- **Demand-Driven Dynamic Scaling (`database/repository.py`, `engine/orchestrator.py`, `engine/radar.py`)**:
  - Add `Repository.get_available_subscriber_demand(max_unconfirmed)` to query the exact count of active, ready subscribers with remaining daily quota per language (`en`, `ar`, `both`).
  - Dynamically scale `limit_per_keyword` in `DiscoveryRadar` and `effective_cycle_cap` / multi-wave iteration in `BotOrchestrator` based on real-time subscriber demand so that every available subscriber receives at least one candidate post per run (scaling seamlessly from 1 user to 1,000+ users).
- **Zero-Cost Cloudflare Worker Telegram Webhook (`workers/telegram_webhook/worker.js`, `wrangler.toml`, `engine/telegram_dispatcher.py`, `main.py`)**:
  - Create a standalone, zero-dependency Cloudflare Worker script (`workers/telegram_webhook/worker.js` + `wrangler.toml`) that handles Telegram `Webhook` POST updates (`/start`, `/help`, `/ready`, `/stop`, `/style`, `/lang`, `/limit`, `/quota`, and inline callback buttons `set_style:*`, `set_lang:*`, `set_limit:*`, `menu:*`, `ready:confirm`, `ack:<tweet_id>`) directly against Turso's HTTP `/v2/pipeline` API in real time.
  - Add `--set-webhook <url>` and `--delete-webhook` CLI flags in `main.py` and `TelegramDispatcher.set_webhook()` / `delete_webhook()` helper methods, plus ensure `sync_subscribers` safely skips `getUpdates` if a webhook is active (or falls back gracefully).

## Ban Risk & Cost Assessment

- **X Account Ban Risk (Minimal / Reduced)**:
  - Fetching `Top` + `Latest` continues to use consolidated Boolean `OR` queries (only 2–4 queries total per cycle) with Gaussian search jitter (`6s–15s`) and immediate Circuit Breaker protection on `401/403/429`.
  - Dynamic cohort sizing preserves the anti-brigading cap per tweet wave (`target_cohort_size_per_tweet = 25..40`) while scaling horizontally across more tweets or waves so X never sees 1,000 replies hit a single tweet simultaneously.
- **Hosting & Service Cost Implications ($0.00 / Zero Cost)**:
  - **Cloudflare Workers Free Tier**: Includes 100,000 requests/day at $0/month, handling all interactive Telegram commands and button clicks 24/7 with zero server maintenance.
  - **GitHub Actions Minutes Saved**: Eliminates the need for `--poll-telegram` in GitHub Actions; scheduled pipeline runs take ~45 seconds per run (~45–90 minutes/month, well within GitHub's 2,000 free minutes).
  - **Turso Cloud & Gemini Flash-Lite**: Both remain well within their free tiers.

## Capabilities

### New Capabilities
- `cloudflare-telegram-webhook`: Serverless Cloudflare Worker webhook handler for real-time 24/7 Telegram command and inline button processing against Turso HTTP API, plus CLI webhook registration (`--set-webhook` / `--delete-webhook`).

### Modified Capabilities
- `virality-scoring`: Hybrid virality scoring that preserves high-engagement viral posts up to 24 hours old alongside emerging high-velocity posts.
- `discovery-radar`: Combined `Top` + `Latest` X search retrieval, maximum tweet age filtering (`max_tweet_age_hours`), and demand-scaled search limits.
- `pipeline-scheduler`: Demand-driven dynamic scaling of scan depth, cycle tweet caps, and multi-wave cohort distribution to guarantee 100% coverage of available subscribers per run.
- `storage-turso`: Repository demand-calculation query (`get_available_subscriber_demand`) and default English (`en`) language preference.
- `telegram-dispatcher`: Default English (`en`) language, interactive multiple-choice inline keyboards for all commands, `setup_bot_commands()`, and `set_webhook` / `delete_webhook` management.

## Impact

- `engine/virality.py`: Updated `calculate_virality_score` with hybrid sustained-engagement scoring for posts up to 24h old.
- `providers/twikit_provider.py` & `engine/radar.py`: `Top` + `Latest` search blending, `max_tweet_age_hours` filter, and dynamic `limit_per_keyword`.
- `database/repository.py` & `database/schema.py`: `get_available_subscriber_demand()`, default `preferred_lang='en'`.
- `engine/orchestrator.py`: Dynamic demand calculation driving radar scan depth and queue processing loop until all available subscribers receive at least one post.
- `engine/telegram_dispatcher.py` & `main.py`: Interactive command keyboards, `set_webhook` / `delete_webhook`, and webhook-safe `sync_subscribers`.
- `workers/telegram_webhook/`: Cloudflare Worker (`worker.js` and `wrangler.toml`) for 24/7 serverless Telegram interactivity.
- `tests/`: Unit and integration tests covering 11–20h viral post scoring, demand-driven scaling for 1,000 subscribers, and webhook management.
