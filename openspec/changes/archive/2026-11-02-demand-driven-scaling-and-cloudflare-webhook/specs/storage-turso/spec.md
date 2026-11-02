# Spec Delta

## ADDED Requirements

### Requirement: Real-Time Subscriber Demand Calculation
The repository MUST provide a query (`get_available_subscriber_demand`) that counts active, ready subscribers whose daily dispatch count is strictly below their `daily_limit`, grouped by language eligibility (`en`, `ar`, and `total`), to drive demand-based radar and orchestrator scaling.

#### Scenario: Calculate demand across English, Arabic, and dual-language subscribers
- **WHEN** `get_available_subscriber_demand` is called with active subscribers in the database
- **THEN** it returns the exact number of available subscribers who can receive English tweets (`en` or `both`), Arabic tweets (`ar` or `both`), and the total unique available subscribers waiting for a post.
