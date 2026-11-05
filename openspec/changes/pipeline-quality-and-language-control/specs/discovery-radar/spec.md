# Spec Delta: discovery-radar

## ADDED Requirements

### Requirement: English-Only Search and Candidate Filtering
The radar MUST restrict keyword search queries strictly to English terms and reject candidate tweets identified as non-English (including Arabic script) before virality scoring or persistence queuing.

#### Scenario: Non-English candidate rejected at radar ingestion
- **WHEN** the radar detects a tweet authored in Arabic or other non-English language during query scanning
- **THEN** the candidate is discarded immediately without inserting it into the queue or spending evaluation quota.

#### Scenario: Radar queries use strictly English search terms
- **WHEN** search query consolidation prepares batches for X API scanning
- **THEN** only configured English search terms are executed, with zero non-English queries sent.
