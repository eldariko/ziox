# Spec Delta

## ADDED Requirements

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
