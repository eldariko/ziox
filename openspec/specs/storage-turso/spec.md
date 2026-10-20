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
