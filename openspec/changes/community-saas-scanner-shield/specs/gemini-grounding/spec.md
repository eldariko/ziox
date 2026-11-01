# Spec Delta

## ADDED Requirements

### Requirement: Multi-Variation Single-Call Response Generation
The system MUST support generating multiple distinct reply variations (`draft_variations`) in a single Gemini API evaluation call, where each variation uses a different rhetorical style (`factual`, `sharp`, `historical_legal`, `rhetorical_question`) so multiple subscribers can respond to the same viral tweet without posting identical copy-paste text.

#### Scenario: Generate multiple distinct variations in one API call without raw URLs in text
- **WHEN** `evaluate_and_draft` is called for a tweet containing a false factual claim with `num_variations=4`
- **THEN** the grounding engine returns a `FactCheckResult` where `is_worth_replying` is `True`, `draft_variations` contains up to 4 distinct replies (each strictly under 220 characters and containing NO raw URLs inside `text` so `Humanizer` can cleanly append a single proof URL without creating duplicate links), and `draft_reply` is populated with the first variation for backward compatibility.

#### Scenario: Proof link diversity across variations
- **WHEN** multiple reply variations are sanitized and prepared for dispatch
- **THEN** the system assigns diversified whitelisted proof URLs across the variations when multiple matching sources exist in `whitelisted_sources.json`.
