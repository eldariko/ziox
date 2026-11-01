# Spec Delta

## ADDED Requirements

### Requirement: Demand-Driven Multi-Subscriber Orchestration and Sharding
The orchestrator MUST synchronize Telegram subscribers at the start of a pipeline run, enforce per-subscriber daily dispatch limits based on subscriber tier (`free` vs. `pro`), and distribute unique AI reply variations across eligible subscribers without duplicate assignments.

#### Scenario: Enforce subscriber daily tier limits and record dispatches
- **WHEN** the pipeline processes a queued viral tweet for active Telegram subscribers
- **THEN** the orchestrator filters out subscribers who have reached their `daily_limit` for the current UTC day or have already received the target `tweet_id`, assigns each remaining subscriber a unique sanitized reply variation, and logs each delivery in the `dispatches` table.

#### Scenario: Skip X scanning when scanner is in cooldown quarantine
- **WHEN** `run_full_pipeline` starts while `scanner_cooldown_until` in `bot_state` is in the future
- **THEN** the orchestrator skips live X keyword scanning to protect the scout account and only processes any pre-existing `DISCOVERED` items in the queue.
