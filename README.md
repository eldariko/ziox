# zioX: AI Fact-Checking, Advocacy & Engagement Agent for X (Twitter)

zioX is an automated intelligence agent and community advocacy platform built to monitor, fact-check, and counter viral misinformation regarding Israel and the Middle East on X (Twitter). The system operates as "the adult in the room" using grounded factual verification, thread state management, strict anti-bot natural cadence, and community-driven human-in-the-loop distribution.

zioX operates in two modes:
- **Autonomous Direct Mode**: Analyzes candidate tweets and directly publishes factual replies via official or session automation with stealth pacing and rate limiting.
- **Community SaaS Telegram Mode**: A single dedicated scout account scans for viral claims; eligible community subscribers receive unique, fact-checked reply variations in Telegram and publish them with a one-tap **X Web Intent** button from their own personal accounts (zero automated bot posts on X).

---

## Key Features

1. **Hybrid Virality Momentum Scoring**:
   Detects breaking scoops as well as sustained viral posts up to 24 hours old without premature linear decay:
   - **Instantaneous Velocity** ($<60\text{ min}$):
     $$\text{Velocity} = \frac{\text{Likes} \times 1.0 + \text{Retweets} \times 2.0 + \text{Replies} \times 1.5}{\text{Age in Minutes} + 10}$$
   - **Sustained Viral Impact** ($1\text{h} - 24\text{h}$):
     $$\text{Sustained} = \frac{\text{Weighted Engagements}}{(\text{Age in Hours})^{0.65} \times 18.0}$$
   - **Effective Virality Score**:
     $$\text{Virality Score} = \max(\text{Velocity}, \text{Sustained})$$
   Tweets are categorized into actionable tiers: `VIRAL_EXPLOSIVE` ($\ge 20$), `VIRAL_HIGH` ($\ge 10$), `VIRAL_EMERGING` ($\ge 5$), and `LOW_TRACTION` ($< 5$).

2. **Combined Top + Latest Search Blending**:
   - Twikit search queries both X's `Top` (sustained viral tweets) and `Latest` (breaking tweets) tabs.
   - Automatically deduplicates tweet IDs and enforces `MAX_TWEET_AGE_HOURS` (default: 24h) to avoid stale discussions.

3. **Demand-Driven Dynamic Scaling (1 to 1,000+ Subscribers)**:
   - Computes real-time subscriber demand across languages (`en`, `ar`, `both`) with a single efficient SQL query (`get_available_subscriber_demand`).
   - Dynamically scales search depth (`limit_per_keyword`) and pipeline cycle tweet caps (`telegram_tweets_per_cycle = ceil(demand / cohort_size)`).
   - Multi-wave dispatch loop (`allow_multi_wave_in_run=True`) ensures 100% of available, ready subscribers receive at least one candidate post per run without starvation or N+1 query bottlenecks.

4. **Thread Continuity State Machine**:
   - **Turn 1 (Root Reply)**: Factual counter-claim with primary source context.
   - **Turn 2 (Follow-up)**: Deepened factual response if the user engages substantively.
   - **Turn 3+ (Disengage)**: Automatically halts engagement to avoid endless circular arguments.
   - **Toxicity / Trolling Shield**: Instantly terminates discussions containing abusive language or bad faith trolling.

5. **Fact Grounding with Gemini 2.5 / 2.0**:
   - Real-time fact extraction, claim analysis, and evidence corroboration.
   - Generates distinct batch reply variations per viral tweet with link/no-link variation ratios (`no_link_variation_ratio = 0.4`).
   - Validates citation URLs and primary evidence links before distribution.

6. **Anti-Bot Humanizer Engine**:
   - Zero em-dashes (`—`) or en-dashes (`–`).
   - Strips canned AI filler phrases (*"It's crucial to understand"*, *"Delving into"*, *"Moreover"*).
   - Enforces a concise 1–3 sentence ceiling.
   - Adapts naturally to the target tweet's language (English, Arabic, Hebrew, French, Spanish).

7. **Serverless 24/7 Cloudflare Worker Telegram Webhook**:
   - Zero-dependency ES Module Cloudflare Worker (`workers/telegram_webhook/worker.js`) responding to Telegram updates in $<100\text{ms}$.
   - Executes interactive command menus and button callbacks directly against Turso Cloud HTTP API (`/v2/pipeline`).
   - Runs 24/7 at $0.00 cost within Cloudflare Workers' free tier (100k requests/day) without consuming GitHub Actions minutes.

8. **Enterprise Logging & Credential Protection**:
   - Built-in `SensitiveDataRedactor` logging filter automatically masks Telegram Bot Tokens (`bot[REDACTED]`) across all logs, console outputs, and exceptions.
   - Mutes chatty external HTTP loggers (`httpx`, `httpcore`, `urllib3`) to prevent sensitive URL credential leakage.

9. **Scanner Safety Shield & Circuit Breaker**:
   - Consolidates search keywords into Boolean `OR` queries per script to minimize X request volume.
   - Gaussian jitter pacing (`min_search_delay_seconds`, `max_search_delay_seconds`).
   - Automated Circuit Breaker quarantines the scanner account for `scanner_cooldown_minutes` (default 12 hours) upon receiving HTTP 401, 403, or 429 errors.

---

## Architecture Overview

```
zioX/
├── GEMINI.md                          # Antigravity agent configuration and operational rules
├── pyproject.toml                     # Project metadata and dependencies
├── requirements.txt                   # Pip dependency lockfile
├── .env.example                       # Environment configuration template
├── assets/
│   └── proofs/                        # Verified documents & infographic asset store
├── config/
│   └── settings.py                    # Pydantic v2 application settings and validation
├── database/
│   ├── schema.py                      # SQLite / Turso schema definition
│   ├── repository.py                  # libSQL / SQLite data access layer & migrations
│   └── turso_client.py                # Native HTTP client for Turso Cloud libSQL API
├── providers/
│   ├── base.py                        # Abstract TwitterProvider interface & Tweet data model
│   ├── mock_provider.py               # Deterministic mock provider for offline testing
│   ├── zernio_provider.py             # Zernio REST API integration
│   └── twikit_provider.py             # Direct X session automation provider (Top + Latest blending)
├── engine/
│   ├── security.py                    # Sensitive credential redaction & secure logging
│   ├── virality.py                    # Hybrid virality momentum scoring (velocity + sustained)
│   ├── thread_state.py                # Thread state machine & bad-faith toxicity shield
│   ├── grounding.py                   # Gemini structured reasoning & multi-variation generation
│   ├── humanizer.py                   # Anti-bot tone sanitation and link ratio modulation
│   ├── link_validator.py              # Evidence URL validation and domain health checks
│   ├── radar.py                       # Discovery Radar & Boolean OR query engine
│   ├── telegram_dispatcher.py         # Telegram Bot API integration & interactive menus
│   └── orchestrator.py                # Unified demand-driven pipeline coordinator
├── workers/
│   └── telegram_webhook/              # Serverless Cloudflare Worker for Telegram Webhook
│       ├── worker.js                  # 24/7 webhook handler talking directly to Turso HTTP
│       └── wrangler.toml              # Cloudflare Worker deployment configuration
├── openspec/                          # OpenSpec specifications and archived changes
│   ├── specs/                         # Active capability specifications
│   └── changes/archive/               # Historical change proposals, designs, and tasks
├── tests/                             # Full automated pytest suite (89 passing tests)
└── main.py                            # CLI entry point and daemon runner
```

---

## Getting Started

### 1. Installation

Install project dependencies in your Python virtual environment (Python 3.12+ recommended):
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Configure Environment

Copy `.env.example` to `.env`:
```powershell
Copy-Item .env.example .env
```

Configure your credentials:
- **Gemini AI**: `GEMINI_API_KEY` (Google AI Studio) and optional `GEMINI_MODEL` (default: `gemini-3.5-flash-lite`).
- **Database Backend**:
  - For local development: `DATABASE_PATH=ziox.db` (default SQLite).
  - For cloud/production: `TURSO_DATABASE_URL` (e.g. `libsql://ziox-...turso.io`) and `TURSO_AUTH_TOKEN`.
- **Twitter / X Scout Provider**:
  - `TWITTER_PROVIDER`: `mock` (offline testing), `twikit` (session cookies), or `zernio`.
  - For Twikit: `X_AUTH_TOKEN` and `X_CT0` cookies from a dedicated scout account.
- **Telegram Bot Dispatcher**:
  - `TELEGRAM_BOT_TOKEN`: Telegram bot token from `@BotFather`.
  - `TELEGRAM_CHAT_ID`: Admin Telegram chat ID for operational alerts.
  - `TELEGRAM_REVIEW_ENABLED`: Set to `true` to enable community review cards.
- **Operational Mode**:
  - `DRY_RUN`: Set to `true` to prevent any unintended live publishing to X.

---

## CLI Reference & Operational Commands

### A. System Diagnostics & Status
- Display current database target (Turso / SQLite), available subscriber demand by language, quotas, and recent logs:
  ```powershell
  python main.py --status
  ```
- Run automated unit and integration tests:
  ```powershell
  pytest -v
  ```

### B. Autonomous Pipeline
- Execute the end-to-end demand-driven pipeline (Radar -> Multi-Variation Grounding -> Sharded Dispatch):
  ```powershell
  # Safe dry-run mode (review cards generated without publishing to X)
  python main.py --pipeline

  # Live execution with specific virality threshold
  python main.py --pipeline --live --threshold 5.0

  # Immediate execution without random start jitter
  python main.py --pipeline --live --no-jitter
  ```

### C. Discovery Radar & Queue Management
- Scan keywords and populate the queue with candidate posts:
  ```powershell
  python main.py --radar --min-faves 5
  ```
- Manually queue a specific tweet URL or numeric ID:
  ```powershell
  python main.py --queue-tweet "https://x.com/user/status/1845123456789" --text "Claim text" --author "user" --likes 1200 --retweets 450
  ```
- Inspect currently queued candidate tweets awaiting processing:
  ```powershell
  python main.py --queue-list
  ```
- Process pending tweets with interactive Human-in-the-Loop terminal review:
  ```powershell
  python main.py --process-queue -i
  ```
- Target and evaluate a single tweet end-to-end:
  ```powershell
  python main.py --process-tweet "1845123456789" -i
  ```

### D. Telegram Webhook & Polling Daemon
- **Register Serverless Cloudflare Webhook**:
  ```powershell
  python main.py --set-webhook "https://ziox-telegram-webhook.<subdomain>.workers.dev" --webhook-secret "your_secret_token"
  ```
- **Delete Webhook** (to resume local polling):
  ```powershell
  python main.py --delete-webhook
  ```
- **Run Local Polling Daemon** (for local development or environments without public webhooks):
  ```powershell
  python main.py --poll-telegram --poll-interval 2.0
  ```
- **Single-shot Telegram Sync**:
  ```powershell
  python main.py --sync-telegram
  ```

---

## Community SaaS Telegram Mode

zioX scales community engagement by empowering subscribers to publish fact-checked counter-arguments from their own accounts with a single tap.

### Subscriber Lifecycle

```
[User sends /start]
         │
         ▼
[Pending State (ready_confirmed=0)]
         │
         ├───────────────────────────────────────────┐
         ▼                                           ▼
[Sends /ready or clicks Inline Button]    [Sets preferences: /lang, /style, /limit]
         │                                           │
         ▼                                           │
  [Active Subscriber] ◄──────────────────────────────┘
         │
         ▼
[Receives Sharded Review Card in Telegram]
         │
         ├─── Tap "X Web Intent" ──► Opens X with pre-filled rebuttal
         └─── Tap "I Replied"    ──► Confirms dispatch (ack:<tweet_id>)
```

- **Interactive Commands**: `/start`, `/help`, `/ready`, `/stop`, `/style`, `/lang`, `/limit`, `/quota`.
  - All command replies provide intuitive multiple-choice inline keyboards (`InlineKeyboardMarkup`).
- **Readiness Gate**: New subscribers must explicitly confirm readiness (`/ready` or button) before receiving review cards.
- **Auto-Pause Shield**: To preserve quota and avoid cluttering inactive users, subscribers are auto-paused (`active=0`) if they accumulate `MAX_UNCONFIRMED_DISPATCHES` (default: 5) without pressing "I Replied".
- **Language Preferences**: Supports English (`en` - default), Arabic (`ar`), and bilingual (`both`).

---

## Cloud Deployments

### 1. Cloudflare Worker Telegram Webhook (Zero-Cost 24/7)

The Cloudflare Worker handles all Telegram commands and button callbacks 24/7 with zero cold start latency:

```bash
cd workers/telegram_webhook

# Configure secrets in Cloudflare
npx wrangler secret put TELEGRAM_BOT_TOKEN
npx wrangler secret put TURSO_DATABASE_URL
npx wrangler secret put TURSO_AUTH_TOKEN
npx wrangler secret put TELEGRAM_WEBHOOK_SECRET
npx wrangler secret put TELEGRAM_CHAT_ID

# Deploy worker
npx wrangler deploy

# Register webhook with Telegram
python ../../main.py --set-webhook "https://ziox-telegram-webhook.<your-subdomain>.workers.dev" --webhook-secret "your_secret"
```

### 2. Live Turso Cloud Database

Turso provides distributed libSQL storage accessible via both native Python HTTP calls and Cloudflare Workers:
```bash
turso db create ziox
turso db show ziox --url        # Set as TURSO_DATABASE_URL
turso db tokens create ziox     # Set as TURSO_AUTH_TOKEN
```
When `TURSO_DATABASE_URL` is set in `.env`, zioX automatically uses Turso and applies schema definitions and incremental migrations.

### 3. Scheduled Autonomous Runs via GitHub Actions

`.github/workflows/ziox_cron.yml` executes `main.py --pipeline --live` every 4 hours.

Configure the following GitHub repository secrets:
- `TURSO_DATABASE_URL` & `TURSO_AUTH_TOKEN`
- `GEMINI_API_KEY`
- `X_AUTH_TOKEN` & `X_CT0` (scout account)
- `TELEGRAM_BOT_TOKEN` & `TELEGRAM_CHAT_ID`
- `TWITTER_PROVIDER=twikit`

> [!NOTE]
> When the Cloudflare Worker Webhook is registered, GitHub Actions only needs to run the batch scan and distribution pipeline (`--pipeline`), consuming fewer than 60 total GitHub Actions minutes per month.

---

## Scanner Safety & Ban Mitigation

- **Dedicated Scout Account**: Always use a dedicated scout account for Twikit session automation. Community subscribers never expose their credentials.
- **Request Minimization**: Keywords are merged into consolidated Boolean `OR` queries per script (e.g. 2–4 queries per cycle instead of dozens).
- **Adaptive Jitter**: Random Gaussian delays between search queries (`MIN/MAX_SEARCH_DELAY_SECONDS`) and pipeline execution (`START_JITTER_MAX_MINUTES`) emulate natural human patterns.
- **Automated Circuit Breaker**: If X returns HTTP 401, 403, or 429, the system halts immediately, quarantines the scout account for `SCANNER_COOLDOWN_MINUTES` (12h), and sends an administrative alert to `TELEGRAM_CHAT_ID`.

---

## Documentation & OpenSpec

- `openspec/specs/`: Canonical source-of-truth capability specifications (`discovery-radar`, `virality-scoring`, `cloudflare-telegram-webhook`, `pipeline-scheduler`, `storage-turso`, `telegram-dispatcher`).
- `openspec/changes/archive/`: Historical records of completed changes, proposals, designs, and tasks.
- `.serena/memories/`: Condensed architecture notes and commands for AI agents.
