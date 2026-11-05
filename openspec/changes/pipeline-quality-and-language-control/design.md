# Technical Design: Pipeline Quality, Control, and Language Isolation

## Context

See `proposal.md` for background and problem motivation.

Currently:
1. GitHub Actions workflow (`.github/workflows/ziox_cron.yml`) and PowerShell runner (`scripts/run_pipeline.ps1`) always execute with hardcoded `--start-jitter 20` or `--start-jitter 15`. While `main.py` already supports `--no-jitter`, the orchestration runners do not expose a parameter to enable it during manual runs.
2. In `engine/orchestrator.py`, `Humanizer.diversify_links_for_variations` is called with `validate_links=False`, bypassing `LinkValidator`'s HTTP checks. Several URLs in `assets/proofs/whitelisted_sources.json` have decayed (SSL failures, 403 Forbidden).
3. `config/settings.py` includes Arabic keywords (`"إسرائيل"`, `"غزة"`, `"מساعدات غزة"`). `engine/radar.py` does not filter candidate language at scan time, and `engine/grounding.py` generates Arabic replies if the source is Arabic. When no subscriber has `preferred_lang='ar'`, `sent_count == 0` causes `engine/orchestrator.py` to trigger a fallback directly to `self.telegram.dispatch_review` without checking the recipient's language preference.

## Goals / Non-Goals

**Goals:**
- Provide zero-wait manual execution paths across CI/CD and local environments.
- Guarantee that every URL sent in reply variations is an active, verified HTTP 200..399 endpoint, stripping invalid links rather than dispatching broken 404/403 pages.
- Enforce strict English-only operations throughout keyword search, radar ingestion, and Gemini evaluation/generation.
- Prevent non-English or unassigned candidate posts from leaking to the admin Telegram chat.

**Non-Goals:**
- Supporting multilingual subscriber distribution or non-English fact checks in this release.
- Replacing the lightweight in-house `LinkValidator` with external third-party link checking SaaS.

## Decisions

### 1. Jitter Bypass Control in Workflow and PowerShell
- **Decision**: Add `no_jitter` boolean input in `.github/workflows/ziox_cron.yml` under `workflow_dispatch` (defaulting to `true`). In PowerShell `scripts/run_pipeline.ps1`, add `[switch]$NoJitter`.
- **Rationale**: Scheduled cron triggers continue using jitter to prevent predictable execution footprints, while manual operator triggers run immediately without wasted runner minutes.
- **Alternatives Considered**: Removing jitter entirely across all runs. Rejected because jitter is valuable for automated cron stealth.

### 2. Mandatory Link Validation and Graceful Degradation
- **Decision**: Set `validate_links=True` when invoking `Humanizer.diversify_links_for_variations`. If a link fails HTTP validation or content checks, the system strips the URL from the drafted reply variation and sends a clean text-only variation. Audit and clean `assets/proofs/whitelisted_sources.json` to purge known dead/blocked links.
- **Rationale**: On X (Twitter), a broken URL damages fact-checking credibility immediately and triggers automated spam detection. Clean text replies are far more persuasive than broken 404 links.
- **Alternatives Considered**: Retrying dead links with web search. Rejected as it introduces unbounded latency during pipeline cycles.

### 3. Early Radar Ingestion Filtering for English Only
- **Decision**: Remove Arabic search keywords from `config/settings.py`. In `engine/radar.py`, inspect tweet language metadata (`tweet.lang`) and filter out tweets where `lang != "en"`. Additionally, verify text against Arabic unicode range (`[\u0600-\u06FF]`) to catch untagged Arabic posts.
- **Rationale**: Filtering at the earliest possible stage prevents spending Gemini token quotas and virality scoring compute on non-English content.

### 4. Grounding System Prompt English Constraint
- **Decision**: Update `SYSTEM_PROMPT` in `engine/grounding.py` with an unambiguous directive: "Restrict all evaluation and replies strictly to ENGLISH only, regardless of the source tweet language."
- **Rationale**: Defense in depth to ensure model outputs never output foreign scripts or mixed-language tokens.

### 5. Language-Aware Admin Review Fallback
- **Decision**: In `engine/orchestrator.py`, wrap the fallback call to `self.telegram.dispatch_review` with a language compatibility check against the admin subscriber's `preferred_lang` (retrieved from the repository or environment). If the post language does not match the admin's preference, log the omission and complete the cycle without sending.
- **Rationale**: Fixes the root-cause bug where zero-matched Arabic posts bypassed all subscriber filters and flooded the admin chat.

## Risks / Trade-offs

- **[Risk: Link validation network latency slows down batch pipeline]** → **Mitigation**: `LinkValidator` already implements in-memory caching for repeated domains/URLs and uses short HTTP request timeouts (3.0s).
- **[Risk: Stricter language filtering reduces total candidate volume]** → **Mitigation**: English keywords in the niche generate substantial viral volume; the radar search limits already cap candidate queue depth.
- **[Risk: Admin may miss unassigned tweets during manual review]** → **Mitigation**: Filtered tweets are recorded in the database queue with descriptive status rather than lost.
