---
name: serena-memory
description: MUST be consulted at the beginning and completion of any architectural, planning, code-writing, or refactoring task in zioX. Loads project memories and conventions from .serena/memories, and updates them when architecture or conventions evolve.
---

# Serena Project Memory System

This skill enforces persistent cross-chat memory for the **zioX** project using Serena's memory architecture located in `.serena/memories/`.

## 1. Entry Point & Discovery (Graph Root)

At the beginning of any non-trivial task (planning, coding, refactoring, or debugging):
1. **Always read the entry point memory**: [core.md](file:///C:/Users/User/PycharmProjects/zioX/.serena/memories/core.md)
2. Follow references (`mem:<topic>`) to specific sub-memories as required by the task:
   - [conventions.md](file:///C:/Users/User/PycharmProjects/zioX/.serena/memories/conventions.md) – Coding style, patterns, error handling, typing rules.
   - [tech_stack.md](file:///C:/Users/User/PycharmProjects/zioX/.serena/memories/tech_stack.md) – Dependencies, architecture decisions, database (Turso/libSQL), providers.
   - [suggested_commands.md](file:///C:/Users/User/PycharmProjects/zioX/.serena/memories/suggested_commands.md) – Test, lint, and run commands.
   - [task_completion.md](file:///C:/Users/User/PycharmProjects/zioX/.serena/memories/task_completion.md) – Verification checklist before completing tasks.

## 2. Reading Memories

Memories are Markdown files located at:
`C:\Users\User\PycharmProjects\zioX\.serena\memories\`

You can read them using:
- Built-in `client_view_file` or `view_file` (fastest and most reliable).
- Or via Serena's MCP `serena_repl` (`print(s.mem.read_memory("<name>"))`).

## 3. Updating & Maintaining Memories

When completing a task that introduces:
- New architectural components or subsystems
- New conventions or persistent design decisions
- Changes to dependencies or environment requirements

You **MUST** update the relevant memory file in `.serena/memories/`:
- **Style**: Dense agent notes, concise bullet points, invariants, no filler.
- **Durable**: Capture generalizable rules and architecture, not transient task details.
- **Reference format**: Use `mem:<name>` to link memories together.
- Update [core.md](file:///C:/Users/User/PycharmProjects/zioX/.serena/memories/core.md) if new top-level components or memories are added.
