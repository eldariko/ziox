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
| **Step 5** | **Virality Threshold & Keyword Calibration** | **NEXT** | `config/settings.py`, `engine/virality.py` |
| **Step 6** | **Multi-Turn Thread State & Anti-Troll Rules** | PENDING | `engine/thread_state.py` |
| **Step 7** | **Interactive Human-in-the-Loop Mode** | PENDING | `main.py` |
| **Step 8** | **Live Twitter / X Integration (Zernio/Direct)** | PENDING | `.env`, `providers/zernio_provider.py` |
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

### Step 5: Virality Threshold & Keyword Calibration
* **Goal**: Calibrate search keywords (`Israel`, `Gaza aid`, `IDF`, `Zionism`) and fine-tune the velocity formula threshold to catch fast-moving posts before peak virality.
* **Files**: [`config/settings.py`](file:///C:/Users/User/PycharmProjects/zioX/config/settings.py), [`engine/virality.py`](file:///C:/Users/User/PycharmProjects/zioX/engine/virality.py)
* **Verification Command**: `pytest tests/test_virality.py`

---

### Step 6: Multi-Turn Conversation & Disengagement Tuning
* **Goal**: Validate thread state progression: Turn 1 (Factual rebuttal) $\to$ Turn 2 (Follow-up evidence) $\to$ Turn 3 (Auto-disengage). Instant termination upon detecting abusive or bad-faith trolling.
* **Files**: [`engine/thread_state.py`](file:///C:/Users/User/PycharmProjects/zioX/engine/thread_state.py)
* **Verification Command**: `pytest tests/test_thread_state.py`

---

### Step 7: Interactive Human-in-the-Loop Mode
* **Goal**: Add CLI flag `--interactive` that displays proposed replies for review: `[Y]es to publish / [N]o to skip / [E]dit text`.
* **Files**: [`main.py`](file:///C:/Users/User/PycharmProjects/zioX/main.py)
* **Verification Command**: `python main.py --interactive` in dry-run mode.

---

### Step 8: Live Twitter / X Integration
* **Goal**: Connect live X credentials (via Zernio API or chosen connector) and test live search and reply publishing in staging mode.
* **Files**: [`.env`](file:///C:/Users/User/PycharmProjects/zioX/.env), [`providers/zernio_provider.py`](file:///C:/Users/User/PycharmProjects/zioX/providers/zernio_provider.py)
* **Verification Command**: Fetch live matching tweets from X without publishing.

---

### Step 9: Autonomous Scheduler & Safety Pacing
* **Goal**: Set up scheduled runs (every 2–3 hours) with monthly safety ceilings (20–30 replies/month) and comprehensive audit logging.
* **Files**: `scheduler.py`
* **Verification Command**: Trigger single scheduler cycle and verify database logs.
