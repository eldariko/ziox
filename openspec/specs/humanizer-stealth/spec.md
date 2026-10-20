# Humanizer & Stealth Pacing

## Purpose
Sanitize AI response patterns, maintain authentic human tone, manage X character constraints, and enforce anti-ban rate limiting delays between automated actions.

## Requirements

### Requirement: Anti-AI Text Sanitization
The system MUST strip robotic transitional phrases (e.g., "it is crucial to understand", "delving into", "furthermore", "in conclusion") and ban em-dashes (`—`).

#### Scenario: Sanitize robotic preamble
- **WHEN** the raw model output begins with "It is crucial to understand that"
- **THEN** the humanizer removes the robotic preamble while preserving the factual substance.

#### Scenario: Em-dash replacement
- **WHEN** generated text contains an em-dash (`—`)
- **THEN** the humanizer replaces it with standard punctuation or hyphenation.

### Requirement: Platform Character Length Compliance
The system MUST measure tweet length according to X platform rules: counting HTTP/HTTPS links as 23 characters (t.co length) and wide characters (emojis, CJK) as 2 units, ensuring content stays within the 280-character limit.

#### Scenario: Long text with URL
- **WHEN** a drafted response exceeds 280 weighted characters
- **THEN** the system truncates or re-formats the response to fit within limits without breaking URLs.

### Requirement: Stealth Gaussian Pacing
The system MUST apply randomized Gaussian delay jitter between consecutive reply actions to emulate natural human typing hesitation and avoid bot detection.

#### Scenario: Live pacing delay
- **WHEN** a reply is dispatched in non-dry-run mode
- **THEN** the orchestrator applies a calculated jitter delay within configured min and max bounds.

### Requirement: Link Diversity & Cooldown
The system MUST prevent repeated citations of the same URL across short intervals by enforcing a configurable domain cooldown window.

#### Scenario: Cooldown throttle
- **WHEN** a proposed link was posted within the last cooldown period
- **THEN** the system suppresses the link or selects an alternative to maintain domain diversity.
