# Design

## Context

See `proposal.md` for motivation. Currently:
- `engine/virality.py` divides weighted engagement linearly by `(age_in_minutes + 10)`, which causes viral tweets older than 2–3 hours (e.g., 11 or 20 hours old) to fall below `5.0` unless they have 3,500–6,000+ engagement points.
- `providers/twikit_provider.py` only queries `product="Latest"` with `limit=5` unless `Latest` returns empty, missing high-traction posts in `product="Top"`.
- `engine/orchestrator.py` and `engine/radar.py` use static parameters (`limit_per_keyword=5`, `telegram_tweets_per_cycle=10`, `target_cohort_size_per_tweet=25`), disconnecting scan depth and queue dispatch from the actual number of available subscribers.
- Telegram command interactivity currently relies on `getUpdates` polling, which either adds delay (batch cron) or consumes runner minutes (`--poll-telegram`).

## Goals / Non-Goals

**Goals:**
- Capture both breaking viral posts (`Latest`) and sustained 1–24 hour viral posts (`Top`, including 11h and 20h old posts) without ingesting stale multi-day posts.
- Dynamically scale radar search depth, queue processing caps, and multi-wave cohort iteration based on real-time subscriber demand (`get_available_subscriber_demand`) so 100% of available subscribers receive at least one post per run.
- Provide a zero-cost, 24/7 real-time Telegram Webhook powered by Cloudflare Workers (`workers/telegram_webhook/worker.js`) talking directly to Turso's `/v2/pipeline` HTTP API, plus CLI helpers (`--set-webhook` / `--delete-webhook`).

**Non-Goals:**
- Moving X scanning (Twikit) or Gemini batch grounding into the Cloudflare Worker. Scheduled batch jobs (GitHub Actions or local task scheduler) remain responsible for X scanning and Gemini variation generation, while the Cloudflare Worker handles instant 24/7 Telegram user interactions.

## Decisions

### 1. Hybrid Virality Formula (`engine/virality.py`)
- **Decision**: Compute `weighted_engagements = Likes * 1.0 + Retweets * 2.0 + Replies * 1.5`.
  - Keep instantaneous velocity: `velocity_score = weighted_engagements / (age_in_minutes + 10.0)`.
  - For tweets within the active 24-hour window (`0 < age_in_minutes <= 1440`), compute a sustained hourly momentum score using sub-linear age damping:
    `age_hours = max(1.0, age_in_minutes / 60.0)`
    `sustained_score = weighted_engagements / ((age_hours ** 0.65) * 18.0)`
  - Return `round(max(velocity_score, sustained_score), 2)` for tweets `<= 1440` minutes old (and `velocity_score` for tweets older than 24h).
- **Rationale**:
  - For a fresh 20-minute tweet (100 likes, 50 RTs, 20 replies = 230 pts), `velocity_score = 7.67` dominates (preserving all existing unit tests and behavior for fresh tweets).
  - For an 11-hour-old viral tweet (660 mins) with 400 likes, 100 RTs, 40 replies (`660` weighted points), `(11 ** 0.65) * 18 = 85.6`, giving `sustained_score = 7.71` (`VIRAL_EMERGING` / `VIRAL_HIGH`), whereas the old linear formula gave `0.99`.
  - For a 20-hour-old viral tweet (1,200 mins) with 600 likes, 150 RTs, 60 replies (`990` weighted points), `(20 ** 0.65) * 18 = 126.2`, giving `sustained_score = 7.85`, whereas the old linear formula gave `0.82`.
  - Low-traction older tweets (e.g., 20 likes after 11 hours = 20 pts -> score `0.23`) are still cleanly rejected below `5.0`.

### 2. Blending `Top` + `Latest` Search with `max_tweet_age_hours` (`providers/twikit_provider.py`, `engine/radar.py`)
- **Decision**:
  - In `TwikitTwitterProvider.search_recent_tweets(query, limit=20)`, query both `product="Top"` and `product="Latest"` (each with `count=limit`), merge results deduplicated by `tweet.id`, and filter out tweets whose age exceeds `max_tweet_age_hours` (default `24.0` hours).
- **Rationale**: X's `Top` tab surfaces high-engagement posts from the last 11–20 hours that are actively trending in users' feeds, while `Latest` surfaces breaking posts from the last few minutes/hours. Combining both and filtering at 24h gives maximum viral coverage without replying to week-old threads.

### 3. Demand-Driven Dynamic Scaling (`database/repository.py`, `engine/orchestrator.py`, `engine/radar.py`)
- **Decision**:
  - Add `Repository.get_available_subscriber_demand(max_unconfirmed=5) -> Dict[str, int]` which executes a single SQL query counting active (`active=1`), ready (`ready_confirmed=1`), non-stalled subscribers whose dispatches today are `< daily_limit`, returning `{"en": en_eligible, "ar": ar_eligible, "total": total_eligible}`.
  - At the start of `run_full_pipeline` and `process_queue`, calculate required tweet waves:
    `needed_tweets = max(base_cycle_cap, math.ceil(demand["total"] / cohort_size))`
  - Scale `limit_per_keyword` in `DiscoveryRadar.scan_keywords` dynamically:
    `dynamic_limit_per_query = max(15, min(50, needed_tweets * 2))`
  - In `BotOrchestrator.process_queue`, allow multi-wave iteration within the same run when `demand["total"] > 0`: if all distinct queued tweets have had 1 wave dispatched and available subscribers still remain without a post in this run, continue dispatching additional waves on `DISPATCHED_WAVE` tweets (with fresh Gemini variation batches) until either all available subscribers have received at least one post in this run or no candidate tweets/variations remain.

### 4. Serverless Cloudflare Worker Webhook (`workers/telegram_webhook/worker.js`)
- **Decision**:
  - Build a zero-dependency ES Module Cloudflare Worker (`workers/telegram_webhook/worker.js` + `wrangler.toml`) that:
    1. Verifies `X-Telegram-Bot-Api-Secret-Token` if `env.TELEGRAM_WEBHOOK_SECRET` is set.
    2. Connects directly to `env.TURSO_DATABASE_URL` (`/v2/pipeline`) with `env.TURSO_AUTH_TOKEN` using native `fetch`.
    3. Handles `/start`, `/help`, `/ready`, `/stop`, `/style`, `/lang`, `/limit`, `/quota` and inline callbacks (`set_style:*`, `set_lang:*`, `set_limit:*`, `menu:*`, `ready:confirm`, `ack:<tweet_id>`) with the exact same Hebrew HTML messages and multiple-choice keyboards as `TelegramDispatcher`.
  - Add `TelegramDispatcher.set_webhook(webhook_url, secret_token)` and `delete_webhook()` + CLI flags `--set-webhook` and `--delete-webhook` in `main.py`.
  - In `TelegramDispatcher.sync_subscribers`, if `getUpdates` returns HTTP `409 Conflict` (which Telegram returns when a Webhook is active), log an informational message that Webhook mode is active and continue seamlessly without error.

## Risks / Trade-offs

- **[Risk] Telegram returns HTTP 409 Conflict on `getUpdates` when Webhook is active** → **Mitigation**: `TelegramDispatcher.sync_subscribers` gracefully catches HTTP 409 (or checks webhook status) and skips `getUpdates` polling when Cloudflare Worker webhook is handling live updates directly in Turso.
- **[Risk] Large subscriber count (1,000) when only a few viral tweets (e.g. 5) are found** → **Mitigation**: Multi-wave loop in `process_queue` can run additional waves on those 5 tweets within the same cycle so remaining available subscribers still get served without needing 40 distinct viral tweets.
