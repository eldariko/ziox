# Spec Delta

## ADDED Requirements

### Requirement: Multi-User Subscriber and Dispatch Ledger Schema
The repository MUST maintain relational tables for Telegram community subscribers (`subscribers`), per-user tweet dispatch tracking (`dispatches`), and key-value operational state (`bot_state`) across both local SQLite and remote Turso Cloud SQLite.

#### Scenario: Subscriber registration and tier persistence
- **WHEN** a new user registers via `/start` on Telegram
- **THEN** the repository inserts or reactivates their `chat_id` in `subscribers` with `active = 1`, default `tier = 'free'`, `daily_limit`, and `preferred_style = 'any'`.

#### Scenario: Prevent duplicate tweet dispatch or identical variation reuse
- **WHEN** a tweet variation is dispatched to a subscriber `chat_id`
- **THEN** the repository records `(tweet_id, chat_id, variation_hash, dispatched_at)` in `dispatches` and prevents sending the same `tweet_id` to the same `chat_id` again or reusing the same `variation_hash` for another subscriber on that `tweet_id`.

#### Scenario: Track Telegram update offset and scanner cooldown state
- **WHEN** the system polls Telegram `getUpdates` or trips a scanner circuit breaker
- **THEN** the repository stores and retrieves `telegram_last_update_id` and `scanner_cooldown_until` in the `bot_state` table.
