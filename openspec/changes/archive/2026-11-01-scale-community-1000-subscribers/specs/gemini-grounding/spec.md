# Spec Delta

## ADDED Requirements

### Requirement: High-Capacity Batch Variation Generation
The grounding engine MUST support generating large sets of unique reply variations (`generate_variations_batch`) for a single viral tweet to serve subscriber cohorts of arbitrary size (from 5 to 50+ subscribers per wave) by executing bounded Gemini batch calls and excluding previously generated phrasings across batches.

#### Scenario: Single-batch generation up to per-call cap
- **WHEN** the orchestrator requests `N` variations where `N` is within `max_variations_per_gemini_call` (e.g., 10)
- **THEN** the grounding engine requests `N` distinct rhetorical variations in a single structured JSON call, each strictly under 220 characters with no inline URLs.

#### Scenario: Multi-batch generation for large cohorts
- **WHEN** the orchestrator requests `N` variations exceeding `max_variations_per_gemini_call` (e.g., 25 variations for a cohort of 25 subscribers)
- **THEN** the grounding engine executes sequential batch calls, passing previously generated variation texts as excluded phrasings so every returned variation has a unique hash and distinct angle.
