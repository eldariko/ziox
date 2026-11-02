# Tech Stack

- **Runtime**: Python 3.12+ (local active venv runs Python 3.14 on Windows) + Cloudflare Workers ES Module JavaScript (`workers/telegram_webhook/worker.js`) for serverless Telegram webhook.
- **Package & Dependency Management**: setuptools build backend (pyproject.toml), dependencies managed via .venv.
- **Core Libraries**:
  - google-genai: LLM grounding and response generation (Gemini).
  - pydantic & pydantic-settings: Structured configuration, validation, and schemas.
  - httpx: Async HTTP client for external APIs, Telegram Bot API, and Turso calls.
  - twikit: Twitter/X direct session provider and scraper integration (`Top` + `Latest` search blending).
  - python-dotenv: Environment configuration loading.
- **Testing**: pytest (v8.0+).
- **Automation & Scheduling**: GitHub Actions cron pipeline + Telegram Web Intent Dispatcher + Cloudflare Worker Telegram Webhook.
- **Database**: Turso/libSQL via native HTTP client (`database/turso_client.py` and Cloudflare Worker `/v2/pipeline`) when `TURSO_DATABASE_URL` is set, else local SQLite (`DATABASE_PATH`). Selected in `main.py`.
- **Key env/settings**: TWITTER_PROVIDER (mock|twikit|zernio; GitHub workflow defaults to mock - must set twikit secret), X_AUTH_TOKEN, X_CT0, TURSO_DATABASE_URL, TURSO_AUTH_TOKEN, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID (admin), TELEGRAM_REVIEW_ENABLED, DRY_RUN, MAX_TWEET_AGE_HOURS (default 24.0).
- **Anti-ban settings**: search_min_faves, combine_search_queries, max_keywords_per_query, min/max_search_delay_seconds, scanner_cooldown_minutes, start_jitter_max_minutes. Jitter is secondary protection; primary is dedicated scout account + few requests (GitHub Actions uses datacenter IPs).
- **Scale settings**: variations_per_tweet, max_variations_per_gemini_call, target_cohort_size_per_tweet, telegram_tweets_per_cycle (auto-scales up dynamically when subscriber demand exceeds baseline), no_link_variation_ratio, max_user_daily_limit, max_unconfirmed_dispatches.
- **Cron & Live Chat**: `.github/workflows/ziox_cron.yml` runs `main.py --pipeline --live`; real-time 24/7 Telegram chat interactivity runs at zero cost on Cloudflare Workers (`workers/telegram_webhook/worker.js`) registered via `main.py --set-webhook <url>`, or locally via `main.py --poll-telegram`.
