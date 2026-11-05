# Proposal: Pipeline Quality, Control, and Language Isolation

## Why

During automated and manual runs of the zioX pipeline, three critical operational issues were identified:
1. **Unwanted Startup Delays on Manual Triggers**: When manually triggering the GitHub Actions workflow (`workflow_dispatch`) or PowerShell runner for immediate execution, jobs were forced to wait up to 15-20 minutes due to hardcoded random jitter intended only for scheduled cron cycles.
2. **Broken and Disconnected Citation Links**: Citations attached to draft replies frequently resulted in HTTP 404/403 errors or SSL handshake failures because link validation was disabled (`validate_links=False`) in the orchestrator to save time, while obsolete/broken URLs remained in the whitelisted proof repository without prompt alignment in Gemini.
3. **Language Leakage to Admin and Non-English Content Processing**: Arabic keywords in search configuration caused the discovery radar and Gemini to process Arabic posts; when no Telegram subscribers matched the Arabic language requirement (`sent_count == 0`), an unconstrained fallback routed unassigned Arabic drafts straight to the admin's Telegram account, completely ignoring the admin's configured English preference.

Implementing immediate run control, mandatory live link verification with vault pruning, and strict English-only pipeline filtering resolves these issues immediately.

## What Changes

- **Manual Cron Immediate Execution**:
  - Add a configurable `no_jitter` boolean input (defaulting to `true` for manual triggers) in `.github/workflows/ziox_cron.yml`.
  - Add a `-NoJitter` switch to `scripts/run_pipeline.ps1` to bypass the 15-minute jitter when executing locally.
  - Pass `--no-jitter` to `main.py` whenever manual execution is requested.

- **Mandatory Link Verification & Proof Vault Pruning**:
  - Enforce `validate_links=True` in `engine/orchestrator.py` during reply variation diversification so that no link is attached without verifying HTTP 200..399 status and substantive body content.
  - Gracefully drop broken URLs from the reply text, leaving a clean, high-impact text-only reply instead of a broken 404/403 link.
  - Audit and clean `assets/proofs/whitelisted_sources.json` to remove known broken/blocked URLs (such as expired or 403 endpoints).

- **Strict English Pipeline Isolation & Admin Fallback Fix**:
  - Restrict `search_keywords` in `config/settings.py` exclusively to English search terms, removing Arabic search queries.
  - Add language filtering in `engine/radar.py` to discard candidate tweets identified as non-English (including Arabic) prior to queuing.
  - Enforce English-only reply generation in `engine/grounding.py` system prompts.
  - Fix the Telegram fallback dispatch in `engine/orchestrator.py` so that unassigned or zero-matched posts never leak to the admin chat unless the admin's `preferred_lang` explicitly matches the post language.

## Capabilities

### New Capabilities
*(None - all changes enhance existing core pipeline capabilities)*

### Modified Capabilities
- `pipeline-scheduler`: Add manual immediate run controls (`--no-jitter`) to CI/CD workflows and local PowerShell scripts, bypassing startup delay during manual invocations.
- `link-validator`: Enforce mandatory HTTP accessibility checks before attaching proof links to replies, and prune broken sources from the whitelist repository.
- `discovery-radar`: Restrict search keywords strictly to English and filter out non-English candidate tweets at radar ingestion.
- `gemini-grounding`: Restrict evaluation and response drafts strictly to English language.
- `telegram-dispatcher`: Enforce language checks on administrative fallback dispatches to prevent non-matching language cards from leaking to the admin.

## Impact

- **Affected Files**:
  - `.github/workflows/ziox_cron.yml`
  - `scripts/run_pipeline.ps1`
  - `engine/orchestrator.py`
  - `engine/link_validator.py`
  - `assets/proofs/whitelisted_sources.json`
  - `config/settings.py`
  - `engine/radar.py`
  - `engine/grounding.py`
  - `engine/telegram_notifier.py`
  - Related test suites under `tests/`
- **Ban Risk Assessment**:
  - **Zero / Reduced**: Removing non-working URLs prevents user flags and spam detection on X. Restricting queries to English prevents cross-community brigading triggers.
- **Hosting / Service Cost Implications**:
  - **Neutral / Zero-cost**: Running without jitter uses existing GitHub Actions free-tier minutes with shorter execution times. Link validation uses fast in-memory caching and standard HTTP HEAD/GET probes. No paid APIs added.
