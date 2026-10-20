# Tech Stack

- **Runtime**: Python 3.12+ (local active venv runs Python 3.14 on Windows).
- **Package & Dependency Management**: setuptools build backend (pyproject.toml), dependencies managed via .venv.
- **Core Libraries**:
  - google-genai: LLM grounding and response generation (Gemini).
  - pydantic & pydantic-settings: Structured configuration, validation, and schemas.
  - httpx: Async HTTP client for external APIs / Turso database calls.
  - 	wikit: Twitter/X API provider and scraper integration.
  - python-dotenv: Environment configuration loading.
- **Testing**: pytest (v8.0+).
