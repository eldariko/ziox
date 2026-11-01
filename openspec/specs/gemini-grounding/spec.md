# Gemini Grounding & Fact Checking

## Purpose
Integrate Google Gemini API with web search grounding to evaluate tweet claims, verify facts, and produce objective citations.

## Requirements

### Requirement: Free-Tier Gemini Connectivity
The system MUST connect to the Google Gemini API using configured API keys and evaluate tweets using the designated model (`gemini-2.5-flash` or compatible).

#### Scenario: Successful claim evaluation
- **WHEN** the grounding engine evaluates a tweet claim with valid API credentials
- **THEN** it returns a structured evaluation containing stance, factual verdict, and confidence.

### Requirement: Google Search Grounding and Web Citations
The system MUST leverage Google Search Grounding tools to verify claims against authoritative web sources and attach citations.

#### Scenario: Grounded response generation
- **WHEN** a claim requires external factual verification
- **THEN** Gemini executes Google Search queries and includes grounded source URLs in the response.

### Requirement: Structured Response Verdicts
The system MUST parse and structure the model's output into consistent machine-readable fields (claim, factual verdict, proposed response, citations).

#### Scenario: Invalid model output handling
- **WHEN** the Gemini model returns malformed or incomplete output
- **THEN** the grounding engine falls back safely without crashing the execution pipeline.

### Requirement: Multi-Variation Single-Call Response Generation
The system MUST support generating multiple distinct reply variations (`draft_variations`) in a single Gemini API evaluation call, where each variation uses a different rhetorical style (`factual`, `sharp`, `historical_legal`, `rhetorical_question`) so multiple subscribers can respond to the same viral tweet without posting identical copy-paste text.

#### Scenario: Generate multiple distinct variations in one API call without raw URLs in text
- **WHEN** `evaluate_and_draft` is called for a tweet containing a false factual claim with `num_variations=4`
- **THEN** the grounding engine returns a `FactCheckResult` where `is_worth_replying` is `True`, `draft_variations` contains up to 4 distinct replies (each strictly under 220 characters and containing NO raw URLs inside `text` so `Humanizer` can cleanly append a single proof URL without creating duplicate links), and `draft_reply` is populated with the first variation for backward compatibility.

#### Scenario: Proof link diversity across variations
- **WHEN** multiple reply variations are sanitized and prepared for dispatch
- **THEN** the system assigns diversified whitelisted proof URLs across the variations when multiple matching sources exist in `whitelisted_sources.json`.

### Requirement: High-Capacity Batch Variation Generation
The grounding engine MUST support generating large sets of unique reply variations (`generate_variations_batch`) for a single viral tweet to serve subscriber cohorts of arbitrary size (from 5 to 50+ subscribers per wave) by executing bounded Gemini batch calls and excluding previously generated phrasings across batches.

#### Scenario: Single-batch generation up to per-call cap
- **WHEN** the orchestrator requests `N` variations where `N` is within `max_variations_per_gemini_call` (e.g., 10)
- **THEN** the grounding engine requests `N` distinct rhetorical variations in a single structured JSON call, each strictly under 220 characters with no inline URLs.

#### Scenario: Multi-batch generation for large cohorts
- **WHEN** the orchestrator requests `N` variations exceeding `max_variations_per_gemini_call` (e.g., 25 variations for a cohort of 25 subscribers)
- **THEN** the grounding engine executes sequential batch calls, passing previously generated variation texts as excluded phrasings so every returned variation has a unique hash and distinct angle.
