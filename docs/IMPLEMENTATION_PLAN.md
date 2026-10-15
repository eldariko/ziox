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
| **Step 8A** | **Decoupled Discovery Radar & Tweet Queue** | **COMPLETED** | `engine/radar.py`, `database/schema.py`, `database/repository.py`, `main.py` |
| **Step 8B** | **Targeted Action & Reply Dispatcher** | **COMPLETED** | `engine/orchestrator.py`, `providers/twikit_provider.py`, `main.py` |
| **Step 9** | **Autonomous Scheduler & Safety Pacing** | **NEXT** | `scheduler.py` |

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

### Step 8A: Decoupled Discovery Radar & Tweet Queue (Completed)
* **Goal**: Implement the Discovery Radar tool (`engine/radar.py`) that discovers candidate viral tweets across target keywords (or via manual URL/ID ingestion) and queues them into SQLite with `status='DISCOVERED'`.
* **Result**:
  - Enhanced SQLite schema and repository with status lifecycle (`DISCOVERED`, `APPROVED`, `PUBLISHED`, `SKIPPED`) and automatic migration.
  - Implemented `DiscoveryRadar` with regex-based URL parsing, virality calculation, and deduplication.
  - Added CLI options `--queue-tweet`, `--queue-list`, and `--radar`.
  - Comprehensive unit test suite: 17/17 passing tests (`tests/test_radar.py`).

---

### Step 8B: Targeted Action & Reply Dispatcher (Completed)
* **Goal**: Implement the Targeted Action/Responder tool that pulls `DISCOVERED` tweets from the queue, evaluates thread state, runs Gemini Google Search grounding, humanizes the response, and posts the reply via an authenticated session.
* **Result**:
  - Implemented `TwikitTwitterProvider` in [`providers/twikit_provider.py`](file:///C:/Users/User/PycharmProjects/zioX/providers/twikit_provider.py) supporting direct session cookie authentication (`auth_token`, `ct0`, `cookies.json`), overcoming third-party API reply limitations.
  - Added `process_queue()` to [`engine/orchestrator.py`](file:///C:/Users/User/PycharmProjects/zioX/engine/orchestrator.py) supporting batch queue processing and targeted single tweet execution (`target_tweet_id`).
  - Added CLI commands `--process-queue` and `--process-tweet <url_or_id>`.
  - Comprehensive unit test suite: 20/20 passing tests (`tests/test_responder.py`). Tested live queue processing against real Gemini API with automatic rate-limit backoff.

---

### Step 9: Autonomous Scheduler & Safety Pacing (Next)
* **Goal**: Set up scheduled runs (every 2–3 hours) with monthly safety ceilings (20–30 replies/month) and comprehensive audit logging.
* **Files**: `scheduler.py`
* **Verification Command**: Trigger single scheduler cycle and verify database logs.
