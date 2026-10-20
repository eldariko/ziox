# zioX Core Architecture

AI-powered fact-checking, advocacy, and engagement bot for X (Twitter). Monitors discussions, verifies claims, humanizes replies, and posts authoritative counter-arguments or context.

## References

- Technical architecture and dependencies: mem:tech_stack
- Development, testing, and system commands: mem:suggested_commands
- Code style, design patterns, and structure: mem:conventions
- Verification checklist for completed tasks: mem:task_completion

## Core Subsystems

- engine/orchestrator.py: Pipeline coordination connecting radar, analysis, verification, humanizer, and posting.
- engine/radar.py: Monitors timeline and searches for relevant narratives and claims.
- engine/grounding.py: Fact-checking and grounding engine powered by Gemini.
- engine/humanizer.py: Style, tone modulation, and anti-bot stealth heuristics.
- engine/link_validator.py: Validates evidence URLs and citation links.
- providers/: Interfaces to social platform backends (	wikit_provider.py, mock_provider.py).
- database/: Storage & state tracking with Turso/libSQL (	urso_client.py, 
epository.py).
