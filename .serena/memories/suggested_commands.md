# Suggested Commands

Run all commands from the project root using PowerShell or Windows command line:

- **Run Test Suite**:
  - .\.venv\Scripts\pytest.exe
- **Run Individual Test File**:
  - .\.venv\Scripts\pytest.exe tests/test_e2e_pipeline.py
- **Run Pipeline Script**:
  - powershell -File scripts/run_pipeline.ps1
- **Main CLI Entrypoint**:
  - .\.venv\Scripts\python.exe main.py
- **Serena Health & Memory Checks**:
  - serena memories check
  - serena project health-check .
- **Unified pipeline (live)**: .\.venv\Scripts\python.exe main.py --pipeline --live [--start-jitter N]
- **Radar only**: .\.venv\Scripts\python.exe main.py --radar --min-faves 20
- **Process queue**: main.py --process-queue
- **Telegram sync once**: main.py --sync-telegram
- **Telegram real-time daemon**: main.py --poll-telegram --poll-interval 10
- **Register Cloudflare Telegram Webhook**: .\.venv\Scripts\python.exe main.py --set-webhook https://<worker>.<subdomain>.workers.dev [--webhook-secret <secret>]
- **Remove Telegram Webhook (revert to polling)**: .\.venv\Scripts\python.exe main.py --delete-webhook
- **Deploy Cloudflare Worker**: cd workers/telegram_webhook && npx wrangler deploy
- **Status (shows active DB)**: main.py --status
- **OpenSpec**: openspec list --json; openspec validate --specs; openspec archive <change> --yes (syncs deltas then archives)
- Use .\.venv\Scripts\python.exe -m pytest (global pytest lacks deps).
