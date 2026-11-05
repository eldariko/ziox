# Tasks

## 1. Jitter Bypass Control in Workflow and Automation Scripts

- [x] 1.1 Add `no_jitter` boolean input in `.github/workflows/ziox_cron.yml` under `workflow_dispatch` and conditional flag injection (`--no-jitter`) in the execution step, verifying valid YAML schema.
- [x] 1.2 Add `-NoJitter` switch parameter to `scripts/run_pipeline.ps1` forwarding `--no-jitter` to `main.py`, verifying parameter parsing and command generation.

## 2. Mandatory Live Link Validation & Proof Vault Cleanliness

- [x] 2.1 Audit and clean `assets/proofs/whitelisted_sources.json` to purge expired, SSL-failing, or 403 Forbidden endpoints, verifying valid JSON syntax.
- [x] 2.2 Enforce `validate_links=True` in `engine/orchestrator.py` when calling `Humanizer.diversify_links_for_variations`, ensuring failed link checks strip the URL and preserve clean text replies.
- [x] 2.3 Add unit tests in `tests/test_link_validation_enforcement.py` using `pytest` verifying that broken URLs are purged while preserving valid variations.

## 3. Strict English Ingestion & Grounding Pipeline

- [x] 3.1 Update `config/settings.py` to purge non-English / Arabic search keywords, verifying configuration loading.
- [x] 3.2 Add language tag and Arabic unicode script detection in `engine/radar.py` to reject non-English candidate tweets at scan ingestion, verifying with unit tests in `tests/test_radar_language_filter.py` using `pytest`.
- [x] 3.3 Update `SYSTEM_PROMPT` in `engine/grounding.py` to enforce strict English-only evaluation and reply variation output, verifying with unit tests in `tests/test_grounding_english.py` using `pytest`.

## 4. Language-Aware Admin Review Fallback

- [x] 4.1 Update fallback dispatch logic in `engine/orchestrator.py` to verify the recipient's `preferred_lang` against candidate tweet language before invoking `self.telegram.dispatch_review`, suppressing dispatches on language mismatch.
- [x] 4.2 Add unit tests in `tests/test_orchestrator_language_fallback.py` using `pytest` verifying that unassigned candidate tweets in non-matching languages do not leak to the admin.

## 5. Integration and Regression Verification

- [x] 5.1 Execute the full project test suite using `pytest` to verify that all existing and new tests pass without regressions.
