# Delta for Link Validator

## ADDED Requirements

### Requirement: Bare Homepage Rejection for Non-Whitelisted Domains
The link validator and humanizer link resolver MUST reject bare domain root URLs (e.g., `https://www.timesofisrael.com` or `https://reuters.com/`) unless the root URL is explicitly present in the curated `whitelisted_sources.json` vault.

#### Scenario: Bare news homepage proposed by LLM
- **WHEN** `LinkValidator.is_bare_homepage` or `Humanizer.resolve_valid_link` evaluates `https://www.timesofisrael.com`
- **THEN** it identifies the URL as a non-whitelisted bare homepage and rejects it immediately without issuing network requests.

#### Scenario: Whitelisted root dashboard URL
- **WHEN** `LinkValidator.is_bare_homepage` evaluates `https://gaza-aid-data.gov.il/` which exists in `whitelisted_sources.json`
- **THEN** it permits the URL as an authorized official dashboard.
