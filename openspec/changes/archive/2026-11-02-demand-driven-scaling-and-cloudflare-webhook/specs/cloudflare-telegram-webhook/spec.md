# Spec Delta

## Purpose

Provide a zero-cost, serverless Cloudflare Worker webhook endpoint that processes Telegram commands and inline button callbacks in real time (<100ms) directly against the Turso Cloud HTTP API without consuming GitHub Actions minutes or requiring an always-on server.

## ADDED Requirements

### Requirement: Real-Time Telegram Webhook Processing on Cloudflare Workers
The system SHALL provide a standalone Cloudflare Worker endpoint that receives incoming Telegram `Update` POST payloads, authenticates the request using an optional `X-Telegram-Bot-Api-Secret-Token` header, executes subscriber state updates against Turso's `/v2/pipeline` HTTP API, and sends immediate HTML replies and callback acknowledgments back to the Telegram Bot API.

#### Scenario: User sends /start or /help via Cloudflare Webhook
- **WHEN** Telegram sends a webhook POST containing `/start` or `/help` from a subscriber chat
- **THEN** the Cloudflare Worker upserts the subscriber in Turso with default language `en` and replies immediately with the HTML welcome/help guide and the interactive multiple-choice main menu keyboard.

#### Scenario: User clicks an inline preference button via Cloudflare Webhook
- **WHEN** Telegram sends a webhook POST with `callback_query` data such as `set_style:sharp`, `set_lang:ar`, `set_limit:4`, `ready:confirm`, or `ack:<tweet_id>`
- **THEN** the Cloudflare Worker updates the corresponding record in Turso (`subscribers` or `dispatches`), calls `answerCallbackQuery` immediately, and sends the updated confirmation message.

#### Scenario: Reject unauthorized webhook requests when secret token is configured
- **WHEN** `TELEGRAM_WEBHOOK_SECRET` is configured in the Cloudflare Worker environment and an incoming POST request lacks a matching `X-Telegram-Bot-Api-Secret-Token` header
- **THEN** the Worker returns HTTP `401 Unauthorized` without querying Turso or calling Telegram.

### Requirement: CLI Webhook Registration and Management
The system SHALL provide CLI flags (`--set-webhook <url>` and `--delete-webhook`) and dispatcher methods to register or remove the Cloudflare Worker webhook URL with Telegram's `setWebhook` and `deleteWebhook` APIs, and automatically skip `getUpdates` polling when an active webhook is detected unless explicitly overridden.

#### Scenario: Register Cloudflare Worker URL via CLI
- **WHEN** the operator runs `python main.py --set-webhook https://ziox-bot.example.workers.dev`
- **THEN** the dispatcher calls Telegram `setWebhook` (and registers bot commands via `setMyCommands`) and prints confirmation.
