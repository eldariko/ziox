# Pipeline Orchestrator & Scheduler

## Purpose
Coordinate discovery, evaluation, human review, and response generation across batch runs, interactive CLI sessions, and external scheduled automation.

## Requirements

### Requirement: Multi-Mode Pipeline Execution
The system MUST support distinct operational modes selectable via CLI arguments or environment flags (single, daemon, interactive, radar-only, and respond-only).

#### Scenario: Interactive Human-In-The-Loop Approval
- **WHEN** running in interactive mode
- **THEN** the CLI prompts the operator to approve, edit, or reject each proposed reply.

#### Scenario: Decoupled radar-only execution
- **WHEN** running with the radar-only flag
- **THEN** the system scans and queues candidates without generating or dispatching replies.

### Requirement: Safe Dry-Run Simulation
The system MUST default to `DRY_RUN=True` where API calls, delays, and tweet postings are simulated and logged without interacting with live platform accounts or spending rate quotas.

#### Scenario: Dry-run simulation
- **WHEN** running with dry-run enabled
- **THEN** no live tweets or replies are posted to X and mock responses are logged safely.

### Requirement: Automation Runner & Cron Integration
The system MUST provide standalone automation entry points (e.g., PowerShell pipeline scripts and CI/CD cron workflows) for scheduled background execution.

#### Scenario: Scheduled cycle execution
- **WHEN** triggered by a cron job or external task runner
- **THEN** the pipeline runs an automated cycle, records action logs, and exits with a zero status code.

### Requirement: Telegram Review Channel Integration
The system SHALL support routing interactive human-in-the-loop review alerts to Telegram during automated or scheduled pipeline executions.

#### Scenario: Scheduled pipeline sends Telegram alerts
- **WHEN** the pipeline runs with Telegram notifications configured
- **THEN** high-momentum grounded candidates are dispatched to Telegram with one-tap X Web Intent URLs instead of prompting on CLI standard input.

### Requirement: Demand-Driven Multi-Subscriber Orchestration and Sharding
The orchestrator MUST synchronize Telegram subscribers at the start of a pipeline run, enforce per-subscriber daily dispatch limits based on subscriber tier (`free` vs. `pro`), and distribute unique AI reply variations across eligible subscribers without duplicate assignments.

#### Scenario: Enforce subscriber daily tier limits and record dispatches
- **WHEN** the pipeline processes a queued viral tweet for active Telegram subscribers
- **THEN** the orchestrator filters out subscribers who have reached their `daily_limit` for the current UTC day or have already received the target `tweet_id`, assigns each remaining subscriber a unique sanitized reply variation, and logs each delivery in the `dispatches` table.

#### Scenario: Skip X scanning when scanner is in cooldown quarantine
- **WHEN** `run_full_pipeline` starts while `scanner_cooldown_until` in `bot_state` is in the future
- **THEN** the orchestrator skips live X keyword scanning to protect the scout account and only processes any pre-existing `DISCOVERED` items in the queue.

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
