# Spec Delta

## ADDED Requirements

### Requirement: Interactive Multiple-Choice Command Keyboards and Default English Language
The Telegram dispatcher MUST default new subscribers to English (`en`), register bot commands in Telegram's native menu (`setMyCommands`), and attach interactive multiple-choice inline keyboards to `/start`, `/help`, `/style`, `/lang`, and `/limit` commands with full callback query handling (`set_style:*`, `set_lang:*`, `set_limit:*`, `menu:*`).

#### Scenario: New subscriber defaults to English and receives interactive menu
- **WHEN** a new user sends `/start`
- **THEN** the dispatcher registers `preferred_lang = 'en'` and replies with an interactive inline menu keyboard for readiness, style, language, daily limit, quota, and stop.

#### Scenario: User updates preferences via multiple-choice inline buttons
- **WHEN** a subscriber sends `/style`, `/lang`, or `/limit` and clicks one of the returned inline option buttons
- **THEN** the dispatcher updates the subscriber's preference in the repository, answers the callback query, and confirms the new setting.
