# Storage & Turso Cloud DB Adapter

## Purpose
Provide unified relational persistence across local SQLite databases and remote Turso / libSQL cloud databases using standard HTTP pipelines.

## Requirements

### Requirement: Dual-Mode Persistence
The system MUST support transparent execution on local SQLite file databases or remote Turso cloud endpoints based on configuration settings.

#### Scenario: Fallback to local SQLite
- **WHEN** no Turso credentials are configured
- **THEN** the repository initializes and executes all queries against local SQLite.

#### Scenario: Connect to Turso Cloud
- **WHEN** valid Turso database URL and auth tokens are provided
- **THEN** queries execute over HTTP v2 pipeline requests without external binary dependencies.

### Requirement: Relational Schema & Indices
The repository MUST manage relational tables for discovered tweets (`discovered_tweets`), operational logs (`logs`), thread state (`thread_states`), and link cooldown tracking (`posted_links`).

#### Scenario: Queue status lifecycle
- **WHEN** a discovered tweet is processed and replied to
- **THEN** its status transitions from `DISCOVERED` to `REPLIED` or `SKIPPED`.

### Requirement: Quota and Budget Enforcement
The repository MUST compute current calendar month reply counts and recent posting intervals to enforce monthly limits and anti-ban cooldowns.

#### Scenario: Monthly limit reached
- **WHEN** the count of replies sent in the current month meets or exceeds the monthly quota
- **THEN** further automated replies are blocked until the next quota window.

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

### Requirement: Subscriber Language and Engagement State Schema
The repository MUST store subscriber language preference (`preferred_lang`), readiness verification (`ready_confirmed`), and unconfirmed dispatch streak (`consecutive_unconfirmed`, `total_confirmed_replies`) in `subscribers`, alongside action confirmation state (`confirmed`, `confirmed_at`) in `dispatches`.

#### Scenario: Automatic column migration on startup
- **WHEN** the repository initializes against an existing local SQLite or remote Turso database
- **THEN** any missing columns (`preferred_lang`, `ready_confirmed`, `consecutive_unconfirmed`, `total_confirmed_replies` on `subscribers`, and `confirmed`, `confirmed_at` on `dispatches`) are added automatically without data loss.

#### Scenario: Updating subscriber language preference
- **WHEN** a subscriber updates their language preference to `en`, `ar`, or `both`
- **THEN** the repository persists `preferred_lang` for that `chat_id`.

#### Scenario: Updating subscriber daily limit within ceiling
- **WHEN** a subscriber requests a personal daily limit via `/limit <number>`
- **THEN** the repository updates `daily_limit` clamped between `1` and the centrally managed tier ceiling (`max_user_daily_limit`).

### Requirement: Single-Query Cohort Eligibility Selection
The repository MUST provide a consolidated query (`get_eligible_subscribers_for_tweet`) that returns eligible subscribers for a given `tweet_id` and tweet language (`en` or `ar`) in a single database query without per-subscriber N+1 round-trips.

#### Scenario: Filtering eligible subscribers in a single query
- **WHEN** `get_eligible_subscribers_for_tweet` is called for a target `tweet_id`, language `lang`, and cohort `limit`
- **THEN** it returns only subscribers where `active = 1`, `ready_confirmed = 1`, `preferred_lang` matches `lang` or `'both'`, the subscriber has not already received `tweet_id`, and their dispatches today are strictly below their `daily_limit`, ordered by least-recently-dispatched first.

### Requirement: Readiness Confirmation and Unconfirmed Streak Tracking
The repository MUST track whether each subscriber has confirmed readiness to reply and increment or reset their `consecutive_unconfirmed` counter as dispatches are sent and acknowledged.

#### Scenario: Recording a dispatch increments unconfirmed streak
- **WHEN** a new review card is recorded in `dispatches` for a non-admin subscriber
- **THEN** the subscriber's `consecutive_unconfirmed` counter increments by 1.

#### Scenario: Subscriber confirms they replied to a tweet
- **WHEN** a subscriber confirms action on a dispatched tweet (or confirms readiness)
- **THEN** the dispatch record is marked `confirmed = 1`, `total_confirmed_replies` increments, `consecutive_unconfirmed` resets to `0`, and `ready_confirmed` is set to `1`.
