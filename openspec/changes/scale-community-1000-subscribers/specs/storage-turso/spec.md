# Spec Delta

## ADDED Requirements

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
