# zioX: AI Fact-Checking, Advocacy & Engagement Agent for X (Twitter)

zioX is an automated intelligence agent built to monitor, fact-check, and rebut viral misinformation regarding Israel and the Middle East on X (Twitter). The system operates as "the adult in the room" using grounded factual verification, thread state management, and strict anti-bot natural cadence.

---

## Key Features

1. **Viral Momentum Scoring**: Detects rapidly rising tweets based on dynamic velocity:
   $$\text{Virality Score} = \frac{\text{Likes} \times 1.0 + \text{Retweets} \times 2.0 + \text{Replies} \times 1.5}{\text{Age in Minutes} + 10}$$
2. **Thread Continuity State Machine**:
   - **Turn 1 (Root Reply)**: Factual counter-claim.
   - **Turn 2 (Follow-up)**: Deepened factual response if the user engages substantively.
   - **Turn 3+ (Disengage)**: Automatically halts engagement to avoid endless circular arguments.
   - **Toxicity / Trolling Shield**: Instantly terminates discussions containing abusive language or bad faith trolling.
3. **Fact Grounding with Gemini 2.0 / 1.5**:
   - Real-time fact extraction and corroboration.
   - Structured JSON decision-making (`is_worth_replying`, `verified_facts`, `recommended_link`).
4. **Anti-Bot Humanizer Engine**:
   - Zero em-dashes (`—`) or en-dashes (`–`).
   - Removes canned robotic phrases ("It's crucial to understand", "Delving into", "Moreover").
   - Enforces a concise 1–3 sentence ceiling.
   - Adapts to the target tweet's language (English, French, Spanish, Arabic, Hebrew, etc.).
5. **Dry-Run & Cost Safeguards**:
   - Default `--dry-run` mode ensures zero unintended posts while developing.
   - Hard monthly reply ceiling (default: 30 replies/month) and SQLite deduplication.

---

## Architecture Overview

```
zioX/
├── GEMINI.md                    # Antigravity rules (English enforcement, guidelines)
├── pyproject.toml               # Project metadata & dependencies
├── requirements.txt             # Pip dependency list
├── .env.example                 # Environment configuration template
├── assets/
│   └── proofs/                  # Verified document & infographic store
├── config/
│   └── settings.py              # Pydantic environment configuration
├── database/
│   ├── schema.py                # SQLite schema (threads, processed_tweets, bot_logs)
│   └── repository.py            # SQLite data access repository
├── providers/
│   ├── base.py                  # Abstract Twitter Provider interface & Tweet model
│   ├── mock_provider.py         # Mock provider for safe offline testing
│   └── zernio_provider.py       # Live Zernio REST API integration
├── engine/
│   ├── virality.py              # Virality momentum scoring
│   ├── thread_state.py          # State machine & toxicity guard
│   ├── grounding.py             # Gemini reasoning & fact-checking
│   ├── humanizer.py             # Anti-bot sanitation pipeline
│   └── orchestrator.py          # Unified execution pipeline
├── tests/                       # Unit test suite
└── main.py                      # CLI entry point
```

---

## Getting Started

### 1. Installation
Install project dependencies in your Python virtual environment:
```powershell
pip install -r requirements.txt
```

### 2. Configure Environment
Copy `.env.example` to `.env`:
```powershell
Copy-Item .env.example .env
```
Fill in your credentials:
- `GEMINI_API_KEY`: Google AI Studio API Key.
- `TWITTER_PROVIDER`: `mock` (for testing) or `zernio` (for live deployment).
- `ZERNIO_API_KEY` & `ZERNIO_TWITTER_ACCOUNT_ID` (if using Zernio).

### 3. Running zioX
Run a dry-run test scan:
```powershell
python main.py --run-once
```

Check system status and logs:
```powershell
python main.py --status
```

Run tests:
```powershell
pytest
```
