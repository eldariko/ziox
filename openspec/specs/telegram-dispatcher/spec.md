# telegram-dispatcher Specification

## Purpose

Provides a secure, cost-free notification and review dispatcher that sends drafted advocacy/fact-check responses to Telegram with one-tap X Web Intent URLs.

## Requirements

### Requirement: Telegram Notification Dispatching
The system SHALL support dispatching fact-checked draft replies to designated Telegram chats via the Telegram Bot API using an action-first, scannable HTML review card formatted with native blockquotes, bulleted facts, and tap-to-copy reply snippets.

#### Scenario: Dispatching review notification to Telegram
- **WHEN** a high-momentum tweet is flagged and a grounded reply draft is produced
- **THEN** the system formats an HTML review card containing the target handle, original tweet inside `<blockquote>` tags, the flagged narrative claim, vertical bulleted facts, and the proposed reply inside `<code>` tags, and dispatches it with inline reply buttons to the designated Telegram chat.

### Requirement: One-Tap X Web Intent Link Generation
The system SHALL generate an encoded X Web Intent URL embedded in each Telegram review card to allow instant one-tap browser or app reply.

#### Scenario: User clicks Web Intent button
- **WHEN** the user opens the Web Intent link from Telegram
- **THEN** X opens with `in_reply_to` pointing to the target tweet and the reply draft pre-populated for operator confirmation.

### Requirement: Serverless Subscriber Onboarding via Telegram getUpdates
The system SHALL synchronize subscriber commands (`/start`, `/stop`, `/style <type>`) by polling Telegram's `getUpdates` endpoint with the persisted `offset` cursor at the start of each scheduled run, requiring zero 24/7 webhook servers, and send immediate confirmation messages upon registration or style changes.

#### Scenario: User sends /start to the Telegram bot
- **WHEN** a user sends `/start` to the Telegram bot between cron runs and `sync_subscribers` executes
- **THEN** the user's `chat_id` is stored as active in `subscribers`, an immediate welcome confirmation message is sent to the user (e.g., confirming registration and explaining `/style`), and `telegram_last_update_id` is advanced so the update is not reprocessed.

#### Scenario: User sends /style to update preferred reply persona
- **WHEN** an active subscriber sends `/style <style_name>` (e.g., `/style sharp`) and `sync_subscribers` executes
- **THEN** the subscriber's `preferred_style` is updated in `subscribers` and a confirmation message is immediately sent back to that `chat_id`.

#### Scenario: User sends /stop to unsubscribe
- **WHEN** an active subscriber sends `/stop` to the Telegram bot and `sync_subscribers` executes
- **THEN** the subscriber's record in `subscribers` is updated to `active = 0` and they receive no further review cards.

### Requirement: Unique Per-Subscriber Variation Dispatching
The system SHALL dispatch personalized review cards where each recipient receives a distinct reply variation and Web Intent URL rather than broadcasting identical reply text to all subscribers.

#### Scenario: Dispatching distinct variations to multiple subscribers
- **WHEN** a viral tweet is evaluated with 3 distinct reply variations and 3 active subscribers are eligible
- **THEN** Subscriber 1 receives Variation A, Subscriber 2 receives Variation B, and Subscriber 3 receives Variation C, each with its own encoded `https://x.com/intent/tweet` button.

### Requirement: Admin-Only Scanner Health Alerting
The system SHALL send administrative alert messages strictly to the operator's configured `TELEGRAM_CHAT_ID` (from `.env`) or subscribers with `tier='admin'`, and NEVER to regular end-user subscribers (`tier='free'` or `tier='pro'`), whenever the X scanner circuit breaker is triggered.

#### Scenario: Scanner hits HTTP 429 or 403 challenge
- **WHEN** the X scanner trips the circuit breaker due to rate limiting or session lock
- **THEN** `TelegramDispatcher.send_admin_alert` dispatches the technical warning notification exclusively to the admin `chat_ids` (`TELEGRAM_CHAT_ID` / `tier='admin'`), ensuring regular subscribers never receive internal scanner error messages.

### Requirement: Pre-Activation Readiness Gate and Action Confirmation
The Telegram dispatcher MUST verify subscriber readiness before sending live tweet cards and track subscriber responsiveness via inline callback buttons (`callback_query`) and commands (`/ready`), automatically pausing subscribers who repeatedly ignore dispatched cards.

#### Scenario: New subscriber onboarding requires readiness confirmation
- **WHEN** a non-admin user sends `/start` to the bot
- **THEN** the bot registers the subscriber with `ready_confirmed = 0` and sends a welcome message with an inline button (`✅ אני מוכן להגיב` / callback `ready:confirm`) and `/ready` instruction, withholding tweet dispatches until confirmed.

#### Scenario: Subscriber confirms readiness via button or command
- **WHEN** a subscriber clicks the `ready:confirm` inline button or sends `/ready`
- **THEN** the dispatcher sets `ready_confirmed = 1`, `active = 1`, and `consecutive_unconfirmed = 0`, answers the callback query, and sends a confirmation message.

#### Scenario: Subscriber confirms replying to a dispatched tweet
- **WHEN** a subscriber clicks the `✅ הגבתי ב-X` inline button (`ack:<tweet_id>`) on a review card
- **THEN** the dispatcher marks the dispatch as confirmed, resets `consecutive_unconfirmed = 0`, increments `total_confirmed_replies`, and acknowledges the button tap.

#### Scenario: Auto-pausing unresponsive subscribers
- **WHEN** a non-admin subscriber reaches `max_unconfirmed_dispatches` consecutive unconfirmed cards
- **THEN** the dispatcher pauses the subscriber (`active = 0`, `ready_confirmed = 0`) and sends a notification with a one-tap wake-up button (`🔔 חזרתי - שלח לי פוסטים`) so no further variations are wasted until they confirm readiness again.

### Requirement: Subscriber Language, Quota, and Limit Commands
The Telegram dispatcher MUST support `/lang <en|ar|both>`, `/limit <number>`, and `/quota` commands during `getUpdates` synchronization.

#### Scenario: Subscriber sets language preference
- **WHEN** a subscriber sends `/lang en`, `/lang ar`, or `/lang both`
- **THEN** the dispatcher updates `preferred_lang` in the database and replies with a confirmation message.

#### Scenario: Subscriber adjusts personal daily limit within central ceiling
- **WHEN** a subscriber sends `/limit 4` and the central ceiling `max_user_daily_limit` is `5`
- **THEN** the dispatcher updates the subscriber's `daily_limit` to `4` and confirms the change; if the requested number exceeds `max_user_daily_limit`, it clamps to `max_user_daily_limit` and informs the user.

#### Scenario: Subscriber checks quota status
- **WHEN** a subscriber sends `/quota`
- **THEN** the dispatcher replies with their current daily usage (`dispatched_today / daily_limit`), preferred style, preferred language, and total confirmed replies.

### Requirement: Paginated Update Sync and Blocked-User Handling
The Telegram dispatcher MUST paginate `getUpdates` until all pending updates are consumed and automatically deactivate any subscriber whose chat returns HTTP `403 Forbidden`.

#### Scenario: Paginating more than 100 pending Telegram updates
- **WHEN** more than 100 subscribers send commands or button callbacks between cron cycles
- **THEN** `sync_subscribers` loops with advancing `offset` cursors until Telegram returns an empty batch.

#### Scenario: Subscriber blocks the Telegram bot
- **WHEN** `sendMessage` returns HTTP `403 Forbidden` for a subscriber's `chat_id`
- **THEN** the dispatcher immediately marks that subscriber as `active = 0` in the repository so future cycles skip them.

### Requirement: Continuous Telegram Polling Daemon
The system MUST provide a long-running polling mode (CLI `--poll-telegram` with `--poll-interval`) that repeatedly runs subscriber synchronization so commands (`/start`, `/ready`, `/lang`, `/limit`, `/quota`) and inline callbacks are handled in near real time outside scheduled pipeline runs.

#### Scenario: Daemon processes commands between pipeline runs
- **WHEN** the daemon is started with `--poll-telegram --poll-interval 10`
- **THEN** it invokes subscriber synchronization every 10 seconds until interrupted.

### Requirement: Interactive Multiple-Choice Command Keyboards and Default English Language
The Telegram dispatcher MUST default new subscribers to English (`en`), register bot commands in Telegram's native menu (`setMyCommands`), and attach interactive multiple-choice inline keyboards to `/start`, `/help`, `/style`, `/lang`, and `/limit` commands with full callback query handling (`set_style:*`, `set_lang:*`, `set_limit:*`, `menu:*`).

#### Scenario: New subscriber defaults to English and receives interactive menu
- **WHEN** a new user sends `/start`
- **THEN** the dispatcher registers `preferred_lang = 'en'` and replies with an interactive inline menu keyboard for readiness, style, language, daily limit, quota, and stop.

#### Scenario: User updates preferences via multiple-choice inline buttons
- **WHEN** a subscriber sends `/style`, `/lang`, or `/limit` and clicks one of the returned inline option buttons
- **THEN** the dispatcher updates the subscriber's preference in the repository, answers the callback query, and confirms the new setting.
