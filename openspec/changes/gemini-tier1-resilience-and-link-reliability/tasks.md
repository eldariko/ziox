# Tasks

## 1. Configuration & Tier-1 Model Defaults

- [x] 1.1 Update `config/settings.py`, `.env.example`, `.env`, and `.github/workflows/ziox_cron.yml` to set the default `GEMINI_MODEL` to `gemini-2.5-flash` and add `gemini_fallback_models` configuration (`["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.0-flash"]`).
- [x] 1.2 Wire `fallback_models=settings.gemini_fallback_models` into `GroundingEngine` initialization in `main.py`.

## 2. Multi-Model Fallback, Response Schema & Search Resilience in GroundingEngine

- [x] 2.1 Update `GroundingEngine` in `engine/grounding.py` to accept `fallback_models`, rotate across candidate models on `503`/`429` retry attempts, enforce `response_schema=FactCheckResult` in `GenerateContentConfig`, and preserve `self.search_available` on transient `503` errors.
- [x] 2.2 Update `SYSTEM_PROMPT` and `_normalize_result` in `engine/grounding.py` to forbid and strip bare non-whitelisted root homepage URLs from `recommended_link`.

## 3. Bare Homepage Filtering & Browser Headers in LinkValidator & Humanizer

- [x] 3.1 Add `is_bare_homepage` helper and enhanced browser headers in `engine/link_validator.py`, and integrate bare-homepage rejection in `engine/humanizer.py` (`resolve_valid_link` and `diversify_links_for_variations`).

## 4. Unit Tests & Verification

- [x] 4.1 Add comprehensive unit tests in `tests/test_tier1_grounding_and_links.py` covering multi-model fallback on `503`, `search_available` preservation on `503` vs `429`, `response_schema` configuration, and bare-homepage URL rejection.
- [x] 4.2 Run the full `pytest` suite and PyCharm `lint_files` code inspection to verify zero regressions and clean code analysis.
