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
