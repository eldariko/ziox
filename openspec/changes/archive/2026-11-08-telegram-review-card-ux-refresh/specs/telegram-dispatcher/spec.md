# Spec Delta: telegram-dispatcher

## MODIFIED Requirements

### Requirement: Telegram Notification Dispatching
The system SHALL support dispatching fact-checked draft replies to designated Telegram chats via the Telegram Bot API using an action-first, scannable HTML review card formatted with native blockquotes, bulleted facts, and tap-to-copy reply snippets.

#### Scenario: Dispatching review notification to Telegram
- **WHEN** a high-momentum tweet is flagged and a grounded reply draft is produced
- **THEN** the system formats an HTML review card containing the target handle, original tweet inside `<blockquote>` tags, the flagged narrative claim, vertical bulleted facts, and the proposed reply inside `<code>` tags, and dispatches it with inline reply buttons to the designated Telegram chat.
