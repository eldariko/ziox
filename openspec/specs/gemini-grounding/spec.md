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
