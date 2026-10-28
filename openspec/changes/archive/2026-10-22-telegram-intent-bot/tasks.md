# Tasks: Telegram Bot & Web Intent Dispatcher

## 1. Configuration & Web Intent Encoding

- [x] 1.1 Add Telegram settings (`telegram_bot_token`, `telegram_chat_id`, `telegram_review_enabled`) to `config/settings.py` supporting comma-separated chat IDs and channel IDs, verified by unit tests
- [x] 1.2 Implement X Web Intent URL builder in `engine/telegram_dispatcher.py` using `urllib.parse.quote(..., safe='')` to ensure strict `%20` space encoding and newline preservation, verified by unit tests

## 2. Telegram Dispatcher Engine & Database Deduplication

- [x] 2.1 Implement `TelegramDispatcher` in `engine/telegram_dispatcher.py` with `httpx.AsyncClient`, HTML message formatting, and native `InlineKeyboardMarkup` button (`[ 🚀 צייץ תגובה ב-X ]`), verified by unit tests with mocked Telegram API responses
- [x] 2.2 Wire `TelegramDispatcher` into `BotOrchestrator.run_cycle` to dispatch candidate replies when Telegram review is enabled, and immediately record the tweet as processed in `TursoRepository` to prevent re-dispatching in subsequent cron runs, verified by unit tests

## 3. GitHub Actions & End-to-End Verification

- [x] 3.1 Update `.github/workflows/ziox_cron.yml` to inject `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, and `TELEGRAM_REVIEW_ENABLED` from GitHub Secrets
- [x] 3.2 Create test suite `tests/test_telegram_dispatcher.py` and run full pytest suite (`.venv\Scripts\pytest.exe`) to ensure all tests pass with zero regressions
