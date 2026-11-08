# Proposal: Gemini Tier-1 Resilience, Structured Schema Enforcement, and Link Validation Hardening

## Why
Recent production pipeline logs revealed two operational issues:
1. **Transient 503 Overload Failures & Premature Search Disabling**: During high global demand on the primary Gemini model (`gemini-3.5-flash-lite`), 3 retries against the same overloaded endpoint all returned `503 UNAVAILABLE`, causing the grounding engine to drop down to static keyword fallback (`_fallback_evaluate`) and skip valid factual claims not matching static keywords. Additionally, a bug in `evaluate_and_draft` permanently disabled `self.search_available = False` on transient `503` errors rather than only on `429 RESOURCE_EXHAUSTED` quota errors.
2. **Root Homepage Hallucinations & 403 WAF Rejections**: The LLM occasionally recommended bare domain homepages (e.g., `https://www.timesofisrael.com`) which fail `LinkValidator` with HTTP 403 due to Cloudflare WAF rules on datacenter IPs and carry no specific article evidence.

With the upgrade to Google Cloud Billing **Tier 1** (with a monthly budget allowance), the system can now leverage higher-accuracy primary models (`gemini-2.5-flash`), automatic multi-model fallback chains (`fallback_models`), native Pydantic `response_schema` enforcement, and stricter URL validation rules.

## What Changes
1. **Multi-Model Fallback Chain & Tier-1 Model Defaults (`config/settings.py`, `engine/grounding.py`, `main.py`, `.env.example`, `.github/workflows/ziox_cron.yml`)**:
   - Add `gemini_fallback_models: List[str]` setting (defaulting to `["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.0-flash"]`) and update default primary model to `gemini-2.5-flash`.
   - When `generate_content` encounters `503 UNAVAILABLE` or `429`, automatically rotate through the configured fallback model list across retry attempts before falling back to the internal static vault.
2. **Native Pydantic `response_schema` & Search State Fix (`engine/grounding.py`)**:
   - Pass `response_schema=FactCheckResult` inside `GenerateContentConfig` (when `google.genai.types` is active and search tools do not conflict) to guarantee valid structured JSON matching `FactCheckResult`.
   - Fix `evaluate_and_draft` so `self.search_available` is only disabled for the session on `429` / `RESOURCE_EXHAUSTED`, not on transient `503` server overload.
3. **Selective Cost-Guarded Search Grounding (`engine/grounding.py`)**:
   - Ensure `SYSTEM_PROMPT` strictly forbids bare root/homepage URLs in `recommended_link` (requiring deep paths to official data or `null` so `Humanizer` attaches a verified whitelisted source).
4. **Root-Domain Filter & Browser Headers in `LinkValidator` (`engine/link_validator.py`, `engine/humanizer.py`)**:
   - Reject bare domain root URLs (where path is empty or `/`) unless explicitly in the whitelisted proof vault, avoiding pointless HTTP requests to news homepages like `https://www.timesofisrael.com`.
   - Upgrade `LinkValidator` HTTP request headers with standard browser `Accept-Language` and `Cache-Control` headers to minimize false-positive CDN blocks.

## Impact
- **Affected Specs**: `gemini-grounding`, `link-validator`
- **Affected Code**: `config/settings.py`, `engine/grounding.py`, `engine/link_validator.py`, `engine/humanizer.py`, `main.py`, `.env.example`, `.github/workflows/ziox_cron.yml`, `tests/`
