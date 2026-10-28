# Conventions

- **Development Workflow Protocol**:
  - Always use **OpenSpec** for all feature additions, architecture changes, and task tracking (`openspec propose`, `openspec apply`, `openspec sync specs`, `openspec archive`).
  - Always use **Serena** (LSP, symbolic editing, AST inspection, project memories) for codebase navigation, refactoring, and state retention.
- **Code Architecture**: Modular layer division:
  - config/: Configuration definitions via Pydantic (Settings).
  - database/: Persistence layer (TursoClient, Repository, schema management).
  - engine/: Core logic components (Orchestrator, Radar, Grounding, Humanizer, LinkValidator, ThreadState, Virality).
  - providers/: Provider abstractions and implementations (BaseProvider, TwikitProvider, MockProvider, ZernioProvider, TelegramProvider).
  - tests/: Unit and end-to-end pytest test cases.
- **Typing & Style**:
  - Strict type annotations across public interfaces.
  - Pydantic models for data interchange and validation.
  - Async-first design for I/O operations (HTTP requests, database calls, API polling).
