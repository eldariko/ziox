# Spec Delta

## ADDED Requirements

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
