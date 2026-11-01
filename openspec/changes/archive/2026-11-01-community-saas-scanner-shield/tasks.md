# Tasks

## 1. Phase A: Scanner Safety Shield & Boolean OR Query Consolidation

- [x] 1.1 Add scanner safety and query consolidation settings (`combine_search_queries`, `max_keywords_per_query`, `min_search_delay_seconds`, `max_search_delay_seconds`, `scanner_cooldown_minutes`) to `config/settings.py` and verify configuration loading with `pytest tests/test_radar.py`.
- [x] 1.2 Implement `ScannerCircuitBreakerError` classification (`401`, `403`, `429`, account lock/challenge) in `providers/twikit_provider.py` and `providers/base.py`, and verify with unit tests in `tests/test_radar.py`.
- [x] 1.3 Implement script-aware Boolean `OR` query builder (`DiscoveryRadar.build_consolidated_queries`), Gaussian inter-query search jitter, and immediate circuit-breaker abort in `engine/radar.py`, and verify with `pytest tests/test_radar.py`.

## 2. Phase B: Multi-Variation AI Grounding & Link Diversification

- [x] 2.1 Add `DraftVariation` model, `draft_variations: List[DraftVariation]` field on `FactCheckResult`, and updated multi-angle `SYSTEM_PROMPT` (`factual`, `sharp`, `historical_legal`, `rhetorical_question` — strictly <=220 chars and explicitly forbidding inline URLs inside `text` so links are only provided via `recommended_link`) in `engine/grounding.py`, plus `variations_per_tweet` in `config/settings.py`, and verify backward compatibility with `pytest tests/test_responder.py`.
- [x] 2.2 Implement `Humanizer.diversify_links_for_variations` in `engine/humanizer.py` to strip any accidental inline URLs from `DraftVariation.text`, attach a single distinct whitelisted proof URL per variation, and enforce the 280-char limit, verifying with `pytest tests/test_humanizer.py`.

## 3. Phase C: Multi-User Database Schema & Serverless Telegram Community SaaS

- [x] 3.1 Add `subscribers`, `dispatches`, and `bot_state` table definitions in `database/schema.py` and CRUD/ledger methods (`upsert_subscriber`, `deactivate_subscriber`, `update_subscriber_style`, `get_active_subscribers`, `record_dispatch`, `has_received_tweet`, `get_subscriber_daily_count`, `get_state`, `set_state`) in `database/repository.py`, verifying both local SQLite and Turso mock adapters with `pytest tests/test_repository.py tests/test_turso_adapter.py`.
- [x] 3.2 Implement `TelegramDispatcher.sync_subscribers()` (polling Telegram `getUpdates` for `/start`, `/stop`, `/style` and sending immediate welcome/style-change confirmation messages to the user), per-subscriber unique variation dispatch (`dispatch_variations_to_subscribers`), and `send_admin_alert()` (restricted strictly to `.env` `TELEGRAM_CHAT_ID` / `tier='admin'` subscribers, never regular subscribers) in `engine/telegram_dispatcher.py`, verifying with `pytest tests/test_telegram_dispatcher.py`.
- [x] 3.3 Upgrade `BotOrchestrator` (`run_cycle`, `process_queue`, `run_full_pipeline`) in `engine/orchestrator.py` to check scanner cooldown state, sync Telegram subscribers, distribute unique variations per subscriber respecting `daily_limit` and `dispatches` deduplication, and verify end-to-end execution with `pytest tests/test_e2e_pipeline.py`.
