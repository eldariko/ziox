# Tasks

## 1. Hybrid Virality Scoring & Combined Top + Latest Search

- [x] 1.1 Update `calculate_virality_score` in `engine/virality.py` to compute a hybrid score (max of instantaneous velocity and sub-linear hourly sustained momentum for posts up to 24h old) and verify with unit tests in `tests/test_virality.py` for 11-hour and 20-hour viral tweets.
- [x] 1.2 Add `max_tweet_age_hours` (default `24.0`) to `config/settings.py`, update `TwikitTwitterProvider.search_recent_tweets` in `providers/twikit_provider.py` to query both `product="Top"` and `product="Latest"` and deduplicate by tweet ID, and filter out tweets older than `max_tweet_age_hours` in `DiscoveryRadar.scan_keywords` (`engine/radar.py`), verifying with pytest in `tests/test_radar.py`.

## 2. Real-Time Subscriber Demand & Dynamic Orchestrator Scaling

- [x] 2.1 Implement `Repository.get_available_subscriber_demand(max_unconfirmed=5)` in `database/repository.py` to count active, ready subscribers with remaining daily quota by language (`en`, `ar`, `total`), and verify with unit tests in `tests/test_repository.py`.
- [x] 2.2 Update `BotOrchestrator` (`engine/orchestrator.py`) to compute dynamic scan limits (`limit_per_keyword`), dynamic cycle caps, and multi-wave queue iteration driven by `get_available_subscriber_demand`, ensuring 100% of available subscribers receive at least one candidate post per run (including 1,000-subscriber cohorts), and verify with E2E tests in `tests/test_e2e_pipeline.py`.

## 3. Serverless Cloudflare Worker Telegram Webhook & CLI Integration

- [x] 3.1 Create the zero-dependency Cloudflare Worker Telegram webhook handler in `workers/telegram_webhook/worker.js` and configuration in `workers/telegram_webhook/wrangler.toml` supporting `/start`, `/help`, `/ready`, `/stop`, `/style`, `/lang`, `/limit`, `/quota`, and all inline callback buttons against Turso HTTP `/v2/pipeline`, and verify file structure and syntax.
- [x] 3.2 Add `set_webhook` and `delete_webhook` methods to `TelegramDispatcher` (`engine/telegram_dispatcher.py`), handle HTTP `409 Conflict` gracefully in `sync_subscribers` when a webhook is active, add `--set-webhook`, `--delete-webhook`, and `--webhook-secret` CLI arguments in `main.py`, and verify with unit tests in `tests/test_telegram_dispatcher.py`.
