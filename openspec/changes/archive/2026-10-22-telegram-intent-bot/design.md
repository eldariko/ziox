# Design: Telegram Bot & Web Intent Dispatcher

## Context

zioX currently executes cycles in `engine/orchestrator.py`. While a terminal-based interactive review exists, it requires an operator to be present at the console. Scheduled execution in GitHub Actions runs headlessly.
To enable zero-ban, zero-cost, multi-user deployment, we introduce a `TelegramDispatcher` that dispatches review cards with one-tap X Web Intent links.

## Goals / Non-Goals

**Goals:**
- Provide asynchronous human-in-the-loop review via Telegram notifications.
- Embed one-tap X Web Intent links (`https://x.com/intent/tweet?in_reply_to=<id>&text=<encoded_text>`) inside Telegram `InlineKeyboardMarkup` buttons.
- Use existing `httpx` client to avoid adding heavy third-party Telegram dependencies.
- Zero hosting and proxy costs, 0% ban risk on X.
- Support both individual chat IDs, broadcast Telegram Channels (e.g. `-100...`), and comma-separated recipient lists.
- Prevent duplicate dispatches across recurring GitHub Actions cron runs.

**Non-Goals:**
- Complex bi-directional bot conversational trees or polling webhooks (this phase is notification/review dispatch).
- Browser extension implementation (deferred to Phase 2).

## Decisions

### Decision 1: Lightweight HTTP Telegram Client via `httpx`
- **Choice**: Call Telegram Bot API endpoints directly via `httpx.AsyncClient` (`https://api.telegram.org/bot<token>/sendMessage`).
- **Rationale**: `httpx` is already part of the project dependencies. Adding `python-telegram-bot` would introduce unnecessary bloat.

### Decision 2: HTML Formatting for Telegram Messages
- **Choice**: Use `parse_mode="HTML"` in Telegram API calls.
- **Rationale**: Telegram's MarkdownV2 requires escaping over 18 special punctuation characters, which frequently leads to 400 Bad Request errors on raw tweet texts. HTML (`<b>`, `<i>`, `<code>`) is much more robust for dynamic social media content.

### Decision 3: Prominent Native `InlineKeyboardMarkup` Button
- **Choice**: Send the Web Intent link inside Telegram's `reply_markup` payload as an `inline_keyboard` button (e.g., `[ 🚀 צייץ תגובה ב-X ]`).
- **Rationale**: A native inline button at the bottom of the card is far easier to tap on mobile than an inline text link.

### Decision 4: Standard URL Encoding with `urllib.parse.quote(safe='')`
- **Choice**: Use `urllib.parse.quote(reply_text, safe='')` rather than `quote_plus`.
- **Rationale**: `quote_plus` encodes spaces as `+`, which Twitter/X mobile clients sometimes display literally or misinterpret. Strict percent-encoding (`%20` for spaces, proper newline encoding) ensures seamless rendering in both the X app and web.

### Decision 5: Flexible Chat / Channel Routing
- **Choice**: `telegram_chat_id` supports single IDs, Telegram Channel IDs (`-100...`), or comma-separated lists (`"123,456"`).
- **Rationale**: Setting up a Telegram Channel allows an entire team or community to receive alerts simultaneously without managing a dynamic user database.

### Decision 6: Database Deduplication State
- **Choice**: Mark dispatched candidates in Turso (`repo.save_processed_tweet(...)`) immediately upon successful Telegram dispatch.
- **Rationale**: Prevents subsequent scheduled cron runs (e.g., in GitHub Actions) from repeatedly querying, drafting, and dispatching alerts for the same viral tweet.

## Risks / Trade-offs

- **[Risk] Telegram message text length**:
  - *Mitigation*: Limit target tweet preview snippet to 200 chars and rely on the full preview in the X Web Intent screen.
- **[Risk] URL Length limit in Web Intent**:
  - *Mitigation*: X handles intents up to 280 characters easily. Ensure the grounded reply text does not exceed 280 chars before encoding.
