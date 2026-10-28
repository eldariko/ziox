# Proposal: Telegram Bot & Web Intent Dispatcher

## Why

Currently, automated posting from GitHub Actions or cloud datacenters using session cookies (`twikit`) carries high risk of X account locks, shadowbanning, and datacenter IP blocks. In addition, serving public users with automated posting requires storing private cookies or paying for residential proxies.
A Telegram Bot dispatcher paired with **X Web Intent links (`x.com/intent/tweet`)** allows zioX to run automated radar and Gemini fact-checking for free on any runner, then instantly dispatches review cards to the user on Telegram. With one tap, the user opens X's official mobile/web interface with the reply pre-populated, achieving **0% ban risk**, **zero proxy costs**, and **100% human-in-the-loop control**.

## What Changes

- Add a new lightweight `TelegramDispatcher` engine/provider to format and send review messages to designated Telegram chats via the free Telegram Bot API.
- Each notification includes the target tweet preview, virality momentum, Gemini-grounded draft, and an inline one-tap button linking to `https://x.com/intent/tweet?in_reply_to=<id>&text=<encoded_text>`.
- Extend the `pipeline-scheduler` to support dispatching candidate replies to Telegram when running in non-interactive / scheduled environments instead of prompting on standard input.
- Provide multi-user chat routing support (so multiple users can subscribe to alerts using their Telegram Chat ID).

## Capabilities

### New Capabilities
- `telegram-dispatcher`: Handles formatting, rate-limiting, and dispatching reply recommendations with one-tap X Web Intent URLs via Telegram Bot API.

### Modified Capabilities
- `pipeline-scheduler`: Extends interactive human-in-the-loop mode to support Telegram as an asynchronous review channel alongside the terminal CLI.

## Impact

- **Ban Risk Assessment**: 0% ban risk. All actual posts originate directly from the user's authentic device through the official X app/website via Web Intent.
- **Hosting & Service Costs**: $0.00. The Telegram Bot API is permanently free. No proxies required.
- **Dependencies**: Light async HTTP calls to `api.telegram.org` using existing `httpx` (no heavy third-party Telegram bot frameworks required).
- **Target Files**:
  - `providers/telegram_provider.py` or `engine/telegram_dispatcher.py`
  - `engine/orchestrator.py`
  - `config/settings.py` (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
