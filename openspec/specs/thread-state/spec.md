# Thread State Machine & Safety

## Purpose
Track multi-turn conversation states, limit bot reply depth per thread, and immediately disengage from abusive, harassing, or bad-faith interactions.

## Requirements

### Requirement: Thread Turn Limits
The system MUST enforce a configurable turn limit (default 2 turns) per conversation to prevent endless back-and-forth loops.

#### Scenario: Maximum turns reached
- **WHEN** a conversation reaches the configured maximum number of replies
- **THEN** the system denies further replies and marks the thread status as `CLOSED_MAX_TURNS`.

### Requirement: Abuse and Toxic Troll Detection
The system MUST detect slurs, hate speech, hostile profanity, and bad-faith harassment across English and Arabic using pattern matching.

#### Scenario: Toxic interaction detected
- **WHEN** an incoming reply contains toxic patterns or personal abuse
- **THEN** the thread manager immediately blocks reply generation and marks the thread status as `DROPPED_TOXIC`.

### Requirement: Thread Continuity Permission
The system MUST verify whether an incoming tweet belongs to an active thread and check parent tweet permissions before allowing an automated response.

#### Scenario: Active thread reply permitted
- **WHEN** an incoming tweet is polite, within turn limits, and references a known thread
- **THEN** the thread manager authorizes the reply and increments the turn counter.
