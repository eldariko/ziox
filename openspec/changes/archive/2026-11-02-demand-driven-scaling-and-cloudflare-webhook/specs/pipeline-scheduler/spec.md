# Spec Delta

## MODIFIED Requirements

### Requirement: Horizontal Cohort Sharding and Multi-Wave Dispatching
The orchestrator MUST dynamically scale scan depth, per-cycle tweet caps, and multi-wave cohort distribution based on the real-time count of available, ready subscribers who have remaining daily quota, ensuring that every available subscriber receives at least one candidate post per run (whether 3 or 1,000+ subscribers are active) while preserving per-wave anti-brigading cohort bounds.

#### Scenario: Horizontal sharding across multiple queued tweets
- **WHEN** 100 ready subscribers are eligible and 4 viral tweets are processed in a cycle with `target_cohort_size_per_tweet = 25`
- **THEN** the orchestrator assigns 25 distinct subscribers to each of the 4 tweets using least-recently-dispatched ordering so all 100 subscribers receive a unique variation without overloading a single post.

#### Scenario: Scaling down seamlessly for small subscriber counts
- **WHEN** only 5 ready subscribers are registered and `target_cohort_size_per_tweet = 25`
- **THEN** the orchestrator requests only 5 variations for the tweet and dispatches 1 unique variation to each of the 5 subscribers.

#### Scenario: Dynamic scaling to cover 1,000 available subscribers in a single run
- **WHEN** 1,000 active, ready subscribers have remaining daily quota at the start of a pipeline run
- **THEN** the orchestrator dynamically calculates the required number of tweet waves (`ceil(1000 / target_cohort_size_per_tweet)`), scales the radar search limit and queue cycle cap accordingly, and continues dispatching across queued tweets (and subsequent waves if needed) until all 1,000 available subscribers have received at least one post in that run.
