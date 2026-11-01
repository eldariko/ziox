# Spec Delta

## ADDED Requirements

### Requirement: Horizontal Cohort Sharding and Multi-Wave Dispatching
The orchestrator MUST distribute active, ready subscribers horizontally across multiple viral tweets in each cycle (`telegram_tweets_per_cycle`), sizing each tweet's variation generation batch to the eligible subscriber cohort (`target_cohort_size_per_tweet`) and keeping viral tweets eligible for subsequent waves (`DISPATCHED_WAVE`) when additional subscribers still need dispatches.

#### Scenario: Horizontal sharding across multiple queued tweets
- **WHEN** 100 ready subscribers are eligible and 4 viral tweets are processed in a cycle with `target_cohort_size_per_tweet = 25`
- **THEN** the orchestrator assigns 25 distinct subscribers to each of the 4 tweets using least-recently-dispatched ordering so all 100 subscribers receive a unique variation without overloading a single post.

#### Scenario: Scaling down seamlessly for small subscriber counts
- **WHEN** only 5 ready subscribers are registered and `target_cohort_size_per_tweet = 25`
- **THEN** the orchestrator requests only 5 variations for the tweet and dispatches 1 unique variation to each of the 5 subscribers.
