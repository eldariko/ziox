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
