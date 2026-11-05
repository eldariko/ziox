# Spec Delta: gemini-grounding

## ADDED Requirements

### Requirement: English-Only Evaluation and Draft Output
The grounding engine MUST enforce strict English-only evaluation directives in system prompts and return all proposed reply variations exclusively in the English language.

#### Scenario: Gemini generates English-only variations
- **WHEN** the grounding engine evaluates a candidate tweet for subscriber reply variations
- **THEN** all returned style variations are composed strictly in English, with zero non-English outputs produced.
