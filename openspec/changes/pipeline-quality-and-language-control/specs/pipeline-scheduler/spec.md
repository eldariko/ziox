# Spec Delta: pipeline-scheduler

## ADDED Requirements

### Requirement: Manual Execution Jitter Bypass Control
The system MUST support immediate execution without randomized startup jitter delays when manually invoked via CI/CD workflows or automation runner scripts.

#### Scenario: Manual GitHub Actions trigger with no-jitter
- **WHEN** the GitHub Actions workflow is triggered via workflow_dispatch with `no_jitter=true`
- **THEN** the workflow executes the pipeline runner immediately with `--no-jitter` without delaying execution.

#### Scenario: Manual local PowerShell execution with -NoJitter
- **WHEN** the operator executes `run_pipeline.ps1` with the `-NoJitter` switch
- **THEN** the runner forwards `--no-jitter` to `main.py`, bypassing the default startup delay.
