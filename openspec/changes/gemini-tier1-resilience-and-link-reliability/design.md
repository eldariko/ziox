# Design: Gemini Tier-1 Resilience & Link Reliability

## Context
The `GroundingEngine` in `engine/grounding.py` currently retries the same `self.model_name` 3 times with exponential backoff (2s, 4s, 8s) when encountering `503 UNAVAILABLE`. When a specific model cluster at Google experiences a regional demand spike, retrying the same model within 14 seconds frequently fails all 3 attempts, forcing fallback to `_fallback_evaluate` (which only matches hardcoded topics like aid, partition, LOAC, and hostages).

Furthermore, in `engine/grounding.py`:
```python
if "503" in err_str or "429" in err_str or "UNAVAILABLE" in err_str:
    ...
    if "tools" in config_params:
        config_params.pop("tools", None)
        self.search_available = False
```
A single `503` error permanently disables `self.search_available` for the remainder of the `GroundingEngine` instance lifecycle.

Finally, in the log:
`URL https://www.timesofisrael.com is dead/inaccessible: HTTP 403`
Because the model returned `recommended_link: "https://www.timesofisrael.com"`, `Humanizer.diversify_links_for_variations` copied that `recommended_link` to every variation when `link_pool` was empty, and `LinkValidator` attempted to validate a generic news homepage protected by Cloudflare WAF.

## Decisions

### 1. Multi-Model Fallback Chain in `GroundingEngine`
- `GroundingEngine.__init__` accepts `fallback_models: Optional[List[str]] = None`.
- Build an ordered candidate model sequence starting with `self.model_name` followed by deduplicated entries from `fallback_models` (defaulting to `["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.0-flash"]`).
- On attempt `0`, use candidate model `0` (`self.model_name`). If a `503` / `UNAVAILABLE` / `429` error occurs, the next retry switches to the next model in the candidate sequence while applying backoff.
- This ensures that if `gemini-2.5-flash` or `gemini-3.5-flash-lite` has a demand spike, the immediate retry routes to an independent model pool.

### 2. Strict `response_schema` Enforcement
- In `evaluate_and_draft`, pass `"response_schema": FactCheckResult` in `config_params` when `types is not None` and `"tools"` is not in `config_params` (or alongside tools if supported; if the SDK raises a config error with both tools and `response_schema`, gracefully omit `response_schema` when tools are attached).
- Preserve `self.search_available` across `503 UNAVAILABLE` retries; only set `self.search_available = False` when `429` or `RESOURCE_EXHAUSTED` occurs with search tools active.

### 3. Homepage URL Rejection & Whitelist-Aware Link Validation
- Add `LinkValidator.is_bare_homepage(url: str) -> bool` which detects URLs whose parsed path is `""` or `"/"` (with no query/fragment) unless the URL is explicitly listed in `whitelisted_sources.json` (such as `https://gaza-aid-data.gov.il/`).
- In `GroundingEngine._normalize_result` and `Humanizer.resolve_valid_link`, strip any `recommended_link` that is a bare non-whitelisted homepage (like `https://www.timesofisrael.com` or `https://www.bbc.com`) before HTTP checking, preventing wasted HTTP 403 round-trips and log noise.
- Enhance `SYSTEM_PROMPT` to explicitly instruct Gemini: never invent or provide bare domain homepages (`https://example.com`) in `recommended_link`; provide `null` unless citing a specific deep-linked official report.
