# Tech Stack

- **Runtime**: Python 3.12+ (local active venv runs Python 3.14 on Windows).
- **Package & Dependency Management**: setuptools build backend (pyproject.toml), dependencies managed via .venv.
- **Core Libraries**:
  - google-genai: LLM grounding and response generation (Gemini).
  - pydantic & pydantic-settings: Structured configuration, validation, and schemas.
  - httpx: Async HTTP client for external APIs, Telegram Bot API, and Turso calls.
  - twikit: Twitter/X direct session provider and scraper integration.
  - python-dotenv: Environment configuration loading.
- **Testing**: pytest (v8.0+).
- **Automation & Scheduling**: GitHub Actions cron pipeline + Telegram Web Intent Dispatcher.
- **Database**: Turso/libSQL via native HTTP client (database/turso_client.py) when TURSO_DATABASE_URL is set, else local SQLite (DATABASE_PATH). Selected in main.py.
- **Key env/settings**: TWITTER_PROVIDER (mock|twikit|zernio; GitHub workflow defaults to mock - must set twikit secret), X_AUTH_TOKEN, X_CT0, TURSO_DATABASE_URL, TURSO_AUTH_TOKEN, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID (admin), TELEGRAM_REVIEW_ENABLED, DRY_RUN.
- **Anti-ban settings**: search_min_faves, combine_search_queries, max_keywords_per_query, min/max_search_delay_seconds, scanner_cooldown_minutes, start_jitter_max_minutes. Jitter is secondary protection; primary is dedicated scout account + few requests (GitHub Actions uses datacenter IPs).
- **Scale settings**: variations_per_tweet, max_variations_per_gemini_call, target_cohort_size_per_tweet, telegram_tweets_per_cycle, no_link_variation_ratio, max_user_daily_limit, max_unconfirmed_dispatches.
- **Cron**: .github/workflows/ziox_cron.yml every 4h runs main.py --pipeline --live; Actions only runs during cron, so real-time Telegram commands need --poll-telegram on a persistent host.
