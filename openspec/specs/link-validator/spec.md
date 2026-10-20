# Link Validator & Fact Whitelist

## Purpose
Validate URLs in real-time, ensure sources are live and contain substantive article text, and maintain a curated repository of authoritative factual proof sources.

## Requirements

### Requirement: URL Syntax & Accessibility Validation
The system MUST validate URL format and perform live HTTP checks with browser-like user agents to verify HTTP 200..399 status.

#### Scenario: Broken or dead link
- **WHEN** an external link responds with HTTP 404, 500, or a network timeout
- **THEN** the validator flags the URL as invalid and prevents it from being attached to replies.

### Requirement: Substantive Content Verification
The system MUST check that resolved web pages contain substantive article content rather than empty bodies, paywalls, or bot challenge pages.

#### Scenario: Paywall or challenge page
- **WHEN** an accessible page has fewer than the minimum required word count
- **THEN** the validator rejects the link as non-substantive.

### Requirement: In-Memory Validation Cache
The system MUST cache link verification results during execution cycles to minimize redundant network calls.

#### Scenario: Repeated URL check in same cycle
- **WHEN** a URL has already been verified in the current session
- **THEN** the validator returns the cached result without making a new HTTP request.

### Requirement: Whitelisted Proof Vault
The system MUST support matching topic keywords against a curated proof vault of verified, authoritative sources (e.g. government data, international archives, established news agencies).

#### Scenario: Match keyword to trusted source
- **WHEN** a claim involves documented historical or statistical facts
- **THEN** the system retrieves a matching whitelisted source URL from the vault.
