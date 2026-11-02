# GEMINI / ANTIGRAVITY PROJECT INSTRUCTIONS & RULES

## 1. Language & Hebrew Response Preview Rule (STRICT & FAST)

### Hebrew Content & Preview Policy
- **NO Hebrew in AI Chat**: Never output Hebrew characters or text directly in the AI Chat window. The AI Chat response must always be in English only (short status, confirmations, progress updates, or completion notices).
- **One Hebrew MD file PER agent chat**: Each agent chat/conversation has its own dedicated file: `.agent-output/chat-<ID8>.md`, where `<ID8>` is the first 8 characters of the current Conversation ID (e.g. conversation `e346e474-2039-416b-b2f8-7de59e25e732` -> `.agent-output/chat-e346e474.md`). Never write to another chat's file.
- **ZERO-REWRITE FAST HISTORY WORKFLOW (MANDATORY FOR SPEED)**:
  - **DO NOT** read the existing `.agent-output/chat-<ID8>.md` file or regenerate its previous history in your LLM output tokens!
  - Instead, write **ONLY the new response** to `.agent-output/_new_<ID8>.md` using `client_create_file` (or `client_edit_file`), and then execute:
    `python C:\Users\User\PycharmProjects\zioX\.agent-output\write_response.py <ID8> C:\Users\User\PycharmProjects\zioX\.agent-output\_new_<ID8>.md --cleanup`
  - `write_response.py` automatically wraps the file in `<div dir="rtl">`, adds `# 🟢 תשובה חדשה (Newest Response - [YYYY-MM-DD HH:MM])` if omitted, demotes the previous newest response, and preserves 100% of the unabridged history inside `<details><summary><b>📜 היסטוריית השיחה הקודמת (לחץ להרחבה / קיפול)</b></summary>...</details>` in < 0.05s.
- **Formatting Rules for Hebrew Responses**:
  1. Use standard Markdown formatting; keep code blocks LTR.
  2. Avoid LaTeX math syntax - write formulas in plain text or code blocks.
  3. **Mermaid diagrams with Hebrew (STRICT Anti-Clipping Rule)**:
     - Always use ASCII alphanumeric node IDs (e.g., `A`, `B`, `step1`, `tursoDb`).
     - Always pad Hebrew text labels with non-breaking spaces `&nbsp;` on both sides: `nodeA["&nbsp; תווית בעברית &nbsp;"]`.
     - In diamond/rhombus decision nodes (`{...}`), add line breaks `<br/>` and padding: `decide{"&nbsp; שאלה בעברית? &nbsp;<br/>(פירוט קצר)"}`.
     - Pad edge labels with quotes and spaces: `A -->|"&nbsp; תיאור חץ &nbsp;"| B`.
     - For multi-node flowcharts, add the padding init directive: `%%{init: {'flowchart': {'padding': 15}}}%%`.
  4. Automatically call the PyCharm tool `open_file_in_editor` on `.agent-output/chat-<ID8>.md` so the editor focuses on it (Note: `open_file_in_editor` schema is `{"filePath": ".agent-output/chat-<ID8>.md"}` — call `call_mcp_tool` directly without re-reading the schema JSON).
  5. In the AI Chat, provide only a short English completion notice with a link to the per-chat file.

## 2. Speed & Performance Optimization Rules (ANTI-BOTTLENECK)
- **NO Inline `python -c` with Special Characters in PowerShell**: Never pass multi-line strings, HTML tags (`<br/>`), or ampersands (`&nbsp;`) inside `python -c "..."` in PowerShell. PowerShell reserves `&`, `<`, `>` and causes syntax failures. Always use `client_create_file` / `client_edit_file` directly, or write a temporary `.py` file.
- **Parallel Tool Calls**: Whenever multiple independent files or commands need to be inspected, emit all `view_file` / `run_command` tool calls in a **single parallel turn** rather than sequential turns.
- **Direct MCP Calls**: For known PyCharm MCP tools (`open_file_in_editor` takes `{"filePath": "..."}`), call `call_mcp_tool` directly without wasting a step viewing the `.json` schema file.

## 3. Antigravity Best Practices & Workflow
- **Step-by-Step Interactive Building**: Do not dump the entire monolithic project in one blind step. Build modularly, test each module with the user, and maintain clean separation of concerns.
- **Dry-Run by Default**: Any automation interacting with external social networks (like X/Twitter) must default to --dry-run to protect user accounts, API limits, and ensure safety before live broadcast.
- **Test-Driven & Verifiable**: Verify database schemas, prompt pipelines, and mock ingestion with unit tests.
- **Maintain File Documentation**: Keep docstrings and types updated.

## 4. Project Specifics (zioX)
- Project Name: zioX
- Purpose: Automated X (Twitter) pro-Israel advocacy engine that counters antisemitism, blood libels, and misinformation using verified sources, logical grounding, and anti-detection mechanisms.
- Key Components:
  - Scraper / Ingestion: Uses Twikit to pull trending tweets without official Twitter API keys.
  - Logic Engine (LLM): Gemini API (`gemini-2.5-pro` or equivalent) for claim extraction, refutation strategy, and tweet drafting.
  - Verification & Grounding: Automated lookup using Google Search grounding or whitelisted evidence sources.
  - Stealth & Humanizer: Delays, typing variations, and LLM prompt design to emulate authentic human advocacy and avoid automated bot detection.
- Working Environment:
  - Python 3.12+ (`C:\Users\User\PycharmProjects\zioX\.venv\Scripts\python.exe`)
  - Key libraries: `twikit`, `google-genai`, `pydantic-settings`, `schedule`, `httpx`
