# Tasks

## 1. Telegram Review Card Template Refresh

- [x] 1.1 Update `TelegramDispatcher.format_review_card` in `engine/telegram_dispatcher.py` to use Option A layout with blockquotes (`<blockquote>`), bulleted facts, and tap-to-copy reply block (`<code>`). Verify by running unit tests.
- [x] 1.2 Update test assertions in `tests/test_telegram_dispatcher.py` to validate blockquote tags, bullet point facts, and tap-to-copy code blocks. Verify by running `.\.venv\Scripts\python.exe -m pytest tests/test_telegram_dispatcher.py`.
- [x] 1.3 Verify simulation script `scripts/test_telegram.py` outputs the updated card structure cleanly without escaping or formatting errors.

## 2. Regression & End-to-End Validation

- [x] 2.1 Run full pytest test suite across `tests/` to guarantee zero regressions across the dispatcher and orchestrator pipelines. Verify by running `.\.venv\Scripts\python.exe -m pytest`.
- [x] 2.2 Update Serena memories if any persistent conventions or patterns were changed.
