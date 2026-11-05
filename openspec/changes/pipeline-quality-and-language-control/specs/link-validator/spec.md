# Spec Delta: link-validator

## ADDED Requirements

### Requirement: Mandatory Live Validation Before Attachment
The orchestrator and variation generator MUST strictly enforce live URL validation before appending any URL to a reply variation. If validation fails or times out, the reply draft MUST be preserved and dispatched without the invalid URL.

#### Scenario: Failed link validation results in clean text reply
- **WHEN** a proposed link fails live validation due to HTTP 4xx/5xx, SSL handshake failure, or content check
- **THEN** the system strips the URL from the drafted reply variation and dispatches the clean text-only variation.

### Requirement: Proof Vault Source Health
The whitelisted proof vault MUST maintain strictly active, publicly accessible sources with valid SSL certificates and successful HTTP responses.

#### Scenario: Pruning inaccessible sources from vault
- **WHEN** the proof vault repository is audited
- **THEN** URLs producing SSL failures or HTTP 403 Forbidden are purged or replaced with verified working alternatives.
