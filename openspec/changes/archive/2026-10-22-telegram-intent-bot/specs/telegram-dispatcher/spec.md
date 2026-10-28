# Spec Delta: telegram-dispatcher

## Purpose

Provides a secure, cost-free notification and review dispatcher that sends drafted advocacy/fact-check responses to Telegram with one-tap X Web Intent URLs.

## ADDED Requirements

### Requirement: Telegram Notification Dispatching
The system SHALL support dispatching fact-checked draft replies to designated Telegram chats via the Telegram Bot API.

#### Scenario: Dispatching review notification to Telegram
- **WHEN** a high-momentum tweet is flagged and a grounded reply draft is produced
- **THEN** the system formats a Markdown review card and dispatches it to the configured Telegram chat ID.

### Requirement: One-Tap X Web Intent Link Generation
The system SHALL generate an encoded X Web Intent URL embedded in each Telegram review card to allow instant one-tap browser or app reply.

#### Scenario: User clicks Web Intent button
- **WHEN** the user opens the Web Intent link from Telegram
- **THEN** X opens with `in_reply_to` pointing to the target tweet and the reply draft pre-populated for operator confirmation.
