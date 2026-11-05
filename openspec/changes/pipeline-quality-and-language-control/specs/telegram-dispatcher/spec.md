# Spec Delta: telegram-dispatcher

## ADDED Requirements

### Requirement: Language-Aware Administrative Review Fallback
The orchestrator and Telegram notification dispatcher MUST enforce subscriber language preferences during fallback dispatches, ensuring that unassigned candidate posts are never dispatched to administrative chats unless the candidate language matches the admin's configured preference.

#### Scenario: Non-matching fallback candidate is suppressed
- **WHEN** zero subscribers match a processed candidate tweet and the orchestrator invokes review fallback
- **THEN** the system verifies the admin's `preferred_lang` against the tweet language, suppressing dispatch if languages do not match.
