# Spec Delta: pipeline-scheduler

## ADDED Requirements

### Requirement: Telegram Review Channel Integration
The system SHALL support routing interactive human-in-the-loop review alerts to Telegram during automated or scheduled pipeline executions.

#### Scenario: Scheduled pipeline sends Telegram alerts
- **WHEN** the pipeline runs with Telegram notifications configured
- **THEN** high-momentum grounded candidates are dispatched to Telegram with one-tap X Web Intent URLs instead of prompting on CLI standard input.
