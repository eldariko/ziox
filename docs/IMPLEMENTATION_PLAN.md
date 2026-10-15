# zioX: Step-by-Step Collaborative Implementation Plan

> **Note**: This file serves as the single source of truth for our build roadmap.
> Every step is granular, specifies the exact files touched, and requires your explicit approval before code is committed.

---

## Workflow Agreement
1. **One Step at a Time**: We work strictly sequentially.
2. **Review Before Writing**: I present the plan, diff preview, and touched files first. You approve before any code is modified.
3. **Dry-Run by Default**: Safe simulation mode (`DRY_RUN=true`) remains active until you choose live deployment.
4. **Verifiable**: Each step includes a 30-second verification command.

---

## Master Roadmap & Progress

| Step | Focus Area | Status | Files Touched |
| :--- | :--- | :--- | :--- |
| **Step 1** | **Gemini API & Free-Tier Connectivity** | **COMPLETED** | `.env`, `config/settings.py`, `engine/grounding.py` |
| **Step 2** | **Google Search Grounding & Web Fact Citations** | **COMPLETED** | `engine/grounding.py` |
| **Step 3** | **Advocacy Persona & System Prompt Tuning** | **COMPLETED** | `engine/grounding.py`, `engine/humanizer.py` |
| **Step 4** | **Verified Fact & Whitelisted Links Vault** | **COMPLETED** | `assets/proofs/whitelisted_sources.json`, `engine/humanizer.py` |
| **Step 5** | **Virality Threshold & Keyword Calibration** | **COMPLETED** | `config/settings.py`, `engine/virality.py`, `engine/orchestrator.py` |
| **Step 6** | **Multi-Turn Thread State & Anti-Troll Rules** | **COMPLETED** | `engine/thread_state.py` |
| **Step 7** | **Interactive Human-in-the-Loop Mode** | **COMPLETED** | `main.py`, `engine/orchestrator.py` |
| **Step 8A** | **Decoupled Discovery Radar & Tweet Queue** | **NEXT** | `engine/radar.py`, `database/schema.py`, `database/repository.py` |
| **Step 8B** | **Targeted Action & Reply Dispatcher** | PENDING | `providers/direct_provider.py`, `main.py` |
| **Step 9** | **Autonomous Scheduler & Safety Pacing** | PENDING | `scheduler.py` |

---

## Detailed Step Specifications

### Step 1: Gemini API Connectivity & Free Tier Verification (Completed)
* **Goal**: Connect active Free-Tier key to Google's latest `gemini-3.5-flash-lite` model.
* **Result**: Tested and confirmed with live claim evaluation. 9/9 unit tests passing.

---

### Step 2: Google Search Grounding & Web Citations (Completed)
* **Goal**: Equip `GroundingEngine` with Google Search tool support (`tools=[types.Tool(google_search=types.GoogleSearch())]`) to verify live claims against real-time news, UN records, and government releases.
* **Result**: Implemented with exponential backoff and automatic citation extraction.

---

### Step 3: Advocacy Persona & System Prompt Tuning (Completed)
* **Goal**: Refine prompt voice: "The adult in the room" (rational, composed, authoritative, subtle dry wit). Strict ban on robotic clichés, em-dashes.
* **Language Policy**: Restrict generated replies strictly to **English** and **Arabic** only (Arabic inputs $\to$ natural Arabic; English or other language inputs $\to$ natural English).
* **Result**: Tested against Arabic, English, and non-target languages. 10/10 unit tests passing.

---

### Step 4: Verified Proof & Whitelisted Links Vault (Completed)
* **Goal**: Build a local verified source registry (`whitelisted_sources.json`) containing official primary-source URLs (COGAT aid dashboards, 1947 UN Resolution 181, LOAC legal documents).
* **Result**: Created JSON registry mapping topics & bilingual keywords. Wired into `Humanizer.sanitize()` to auto-attach primary sources in English and Arabic. 11/11 unit tests passing.

---

### Step 5: Virality Threshold & Keyword Calibration (Completed)
* **Goal**: Calibrate search keywords (`Israel`, `Gaza aid`, `IDF`, `Zionism`, `إسرائيل`, `غزة`, `مساعدات غزة`) and fine-tune velocity momentum scoring.
* **Result**: Implemented virality tier classifier (`VIRAL_EXPLOSIVE`, `VIRAL_HIGH`, `VIRAL_EMERGING`). Updated orchestrator to sort and prioritize candidate posts by momentum. 12/12 unit tests passing.

---

### Step 6: Multi-Turn Conversation & Disengagement Tuning (Completed)
* **Goal**: Validate thread state progression: Turn 1 (Factual rebuttal) $\to$ Turn 2 (Follow-up evidence) $\to$ Turn 3 (Auto-disengage). Instant termination upon detecting abusive or bad-faith trolling.
* **Result**: Added comprehensive bilingual (English & Arabic) slur and troll filter patterns. Enforced automatic thread disengagement (`DROPPED_TOXIC`, `COMPLETED`). 13/13 unit tests passing.

---

### Step 7: Interactive Human-in-the-Loop Mode (Completed)
* **Goal**: Add CLI flag `--interactive` that displays proposed replies for review: `[A]pprove & Send / [E]dit Draft / [S]kip Tweet / [Q]uit Cycle`.
* **Result**: Implemented terminal prompt with full context (claim, virality tier, facts, reply). Added text editing, skipping, and graceful exit. 14/14 unit tests passing.

---

### Step 8A: Decoupled Discovery Radar & Tweet Queue (Next)
* **Goal**: Implement the Discovery Radar tool (`engine/radar.py`) that discovers candidate viral tweets across target keywords (or via manual URL/ID ingestion) and queues them into SQLite with `status='DISCOVERED'`.
* **Key Components**:
  - Update SQLite schema & repository with status tracking (`DISCOMMITTED`/`DISCOVERED`, `APPROVED`, `PUBLISHED`, `SKIPPED`).
  - Radar discovery engine capable of ingesting tweets via keyword search or direct tweet URL/ID.
  - CLI command: `python main.py radar --keywords` and `python main.py queue-tweet <url_or_id>`.
* **Files**: [`database/schema.py`](file:///C:/Users/User/PycharmProjects/zioX/database/schema.py), [`database/repository.py`](file:///C:/Users/User/PycharmProjects/zioX/database/repository.py), [`engine/radar.py`](file:///C:/Users/User/PycharmProjects/zioX/engine/radar.py), [`main.py`](file:///C:/Users/User/PycharmProjects/zioX/main.py)
* **Verification Command**: Ingest a sample tweet URL/ID into the DB queue and verify it appears with status `DISCOVERED`.

---

### Step 8B: Targeted Action & Reply Dispatcher (Pending)
* **Goal**: Implement the Targeted Action/Responder tool that pulls `DISCOVERED` tweets from the queue, evaluates thread state, runs Gemini Google Search grounding, humanizes the response, and posts the reply via an authenticated session.
* **Key Components**:
  - Responder module reading from SQLite queue or a specific target tweet ID.
  - Interactive approval or automated dispatch with anti-bot pacing.
  - Direct posting integration (Playwright browser session or authenticated connector).
* **Files**: `engine/orchestrator.py`, `providers/direct_provider.py`, `main.py`
* **Verification Command**: Process a queued tweet in dry-run mode and verify the full pipeline end-to-end.

---

### Step 9: Autonomous Scheduler & Safety Pacing
* **Goal**: Set up scheduled runs (every 2–3 hours) with monthly safety ceilings (20–30 replies/month) and comprehensive audit logging.
* **Files**: `scheduler.py`
* **Verification Command**: Trigger single scheduler cycle and verify database logs.
