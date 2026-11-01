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

### Requirement: Boolean OR Query Consolidation
The system MUST support consolidating multiple search keywords into combined Boolean `OR` search queries grouped by language script (e.g., English vs. Arabic) up to a configurable maximum keywords per query (`max_keywords_per_query`), reducing total X search requests per scan cycle by up to 80%.

#### Scenario: Consolidate English and Arabic keywords into grouped OR queries
- **WHEN** `combine_search_queries` is enabled and `search_keywords` contains 6 English terms and 3 Arabic terms with `max_keywords_per_query=6`
- **THEN** the radar constructs 1 combined English `OR` query (`("Israel" OR "Gaza" OR "IDF" OR "Zionism" OR "Hostages" OR "Middle East")`) and 1 combined Arabic `OR` query (`("إسرائيل" OR "غزة" OR "مساعدات غزة")`) instead of 9 separate search calls.

#### Scenario: Quote multi-word phrases inside OR query
- **WHEN** a keyword contains spaces (e.g., `Middle East` or `مساعدات غزة`)
- **THEN** the query builder wraps each term in double quotes before joining with ` OR `.

### Requirement: Gaussian Search Jitter Between Queries
The system MUST apply a bounded Gaussian (normal distribution) randomized delay between consecutive X search queries instead of a fixed static sleep interval.

#### Scenario: Randomized pause between multi-batch search queries
- **WHEN** the radar executes more than one search query in a cycle and `dry_run` is `False`
- **THEN** the radar sleeps for a Gaussian-distributed duration bounded between `min_search_delay_seconds` and `max_search_delay_seconds` before issuing the next search request.

### Requirement: Scanner Circuit Breaker on Account Danger
The system MUST detect X authentication, account lock, or rate-limit errors (`HTTP 401`, `HTTP 403`, `HTTP 429`, or Twikit challenge/lock exceptions) during scanning and immediately abort the remaining scan cycle to protect the scanner profile.

#### Scenario: Immediate abort on HTTP 429 or 403 during keyword scan
- **WHEN** the provider raises a `ScannerCircuitBreakerError` (due to `401`, `403`, `429`, or account lock) on the first search query
- **THEN** the radar halts immediately without executing subsequent queries, records the cooldown state in persistence, and triggers an admin health alert.

### Requirement: Minimum Engagement Search Filter
The system MUST support an optional `min_faves` search filter (setting `search_min_faves`, CLI `--min-faves`) appended to every X search query so that zero-engagement noise is excluded before virality scoring. A value of 0 SHALL disable the filter.

#### Scenario: Append min_faves to consolidated queries
- **WHEN** `min_faves` is greater than 0
- **THEN** every consolidated Boolean OR query ends with ` min_faves:<N>`.

#### Scenario: Filter disabled by default
- **WHEN** `min_faves` is 0
- **THEN** queries are issued without a `min_faves` clause.
