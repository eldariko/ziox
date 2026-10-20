# Discovery Radar

## Purpose
Scan X / Twitter feeds and search queries for trending or viral tweets matching targeted topics, parse tweet identifiers, and ingest candidate tweets into the persistence queue.

## Requirements

### Requirement: Tweet Identifier and URL Parsing
The system MUST support extracting clean numeric tweet IDs from full X/Twitter URLs, query-string URLs, mobile links, or raw ID strings.

#### Scenario: Parse tweet URL with parameters
- **WHEN** a URL such as `https://x.com/username/status/1845123456789?s=20` is provided
- **THEN** the radar extracts the numeric identifier `1845123456789`.

#### Scenario: Handle raw tweet IDs
- **WHEN** a numeric string like `1845123456789` is provided
- **THEN** the radar returns the ID directly.

### Requirement: Candidate Ingestion and Queuing
The system MUST score candidate tweets using the virality engine and insert them into the repository with `DISCOVERED` status.

#### Scenario: Enqueue manual tweet
- **WHEN** a user or external script enqueues a tweet URL or ID
- **THEN** the tweet metadata is stored in the queue with its initial virality score.

#### Scenario: Ignore duplicate tweets
- **WHEN** a tweet ID that already exists in the queue is enqueued
- **THEN** the radar skips or updates without inserting duplicate records.
