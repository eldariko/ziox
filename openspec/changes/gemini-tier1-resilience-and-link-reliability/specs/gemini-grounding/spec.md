# Delta for Gemini Grounding

## ADDED Requirements

### Requirement: Multi-Model Fallback Chain on API Overload
The grounding engine MUST support a configurable sequence of fallback Gemini models (`fallback_models`) and automatically rotate to the next available model when a `503 UNAVAILABLE` or `429` error occurs during `evaluate_and_draft`.

#### Scenario: Primary model experiences 503 high demand spike
- **WHEN** the primary configured `model_name` returns `503 UNAVAILABLE` on attempt 1
- **THEN** the grounding engine logs the overload warning and retries the request using the next configured fallback model before resorting to the static internal fact vault.

#### Scenario: Search availability preserved across transient 503 errors
- **WHEN** `enable_search` is `True` and the API returns `503 UNAVAILABLE` (server overload, not quota exhaustion)
- **THEN** `self.search_available` remains `True` for subsequent tweet evaluations in the pipeline run, whereas `429 RESOURCE_EXHAUSTED` disables search for the session.

### Requirement: Pydantic Response Schema Enforcement & Bare Homepage Filtering
The grounding engine MUST enforce the `FactCheckResult` Pydantic schema on Gemini JSON responses and strip bare non-whitelisted root homepage URLs from `recommended_link`.

#### Scenario: Model suggests a generic root homepage URL
- **WHEN** Gemini returns a bare domain homepage such as `https://www.timesofisrael.com` in `recommended_link`
- **THEN** `_normalize_result` clears the bare homepage link to `None` so `Humanizer` can cleanly fall back to verified whitelisted sources or linkless output without triggering 403 WAF errors.
