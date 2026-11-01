# Spec Delta

## ADDED Requirements

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
