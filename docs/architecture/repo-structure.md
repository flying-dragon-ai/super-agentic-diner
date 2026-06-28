# Repository Structure

This document defines the project directory boundaries so cleanup work can be
done without touching runtime data, local secrets, or generated assets that are
served by the app.

## Root Entrypoints

| Path | Purpose | Cleanup rule |
|---|---|---|
| `README.md` | Human entrypoint and quick start. | Keep concise; link to detailed docs. |
| `AGENTS.md` | Shared agent instructions and architecture constraints. | Treat as authoritative for agent behavior. |
| `CLAUDE.md`, `GEMINI.md`, `opencode.jsonc` | Tool-specific guidance/config. | Keep only tool-specific differences here. |
| `.env.example` | Safe environment template. | Keep tracked; never add real secrets. |
| `.env`, `.local-consumer.env` | Local credentials/config. | Never commit or delete during cleanup. |
| `coffee_ai.db` | Local SQLite runtime database. | Ignore and preserve unless the user explicitly asks to reset data. |
| `docker-compose.yml`, `Dockerfile`, `deploy/` | Local and deployment runtime entrypoints. | Keep paths stable unless deployment docs are updated together. |

## Source And Runtime Assets

| Path | Purpose | Cleanup rule |
|---|---|---|
| `app/` | FastAPI backend, SQLAlchemy models, services, and served static files. | Do not move business code as part of hygiene cleanup. |
| `app/static/3d/` | Built 3D frontend output served by FastAPI. | Treat as active runtime output; validate bundle references before deleting anything. |
| `app/images/` | Menu images served by `/images`. | Keep tracked if referenced by the app. |
| `frontend/` | React/Vite 3D frontend source. | `frontend/public/` is the source asset tree; build output goes to `app/static/3d/`. |
| `tests/` | Python test suite and focused verification scripts. | Keep tracked; generated caches are ignored. |
| `scripts/` | Database migrations, startup, packaging, and operational checks. | Prefer snake_case names; avoid moving paths without updating docs/tests. |

## Project Knowledge And Agent Assets

| Path | Purpose | Cleanup rule |
|---|---|---|
| `.agents/` | Project A2A skills and MCP wrapper scripts. | Project asset; keep tracked unless a skill is retired. |
| `.codestable/` | Architecture, audits, roadmap, and project knowledge base. | Project asset; keep tracked. |
| `.claude/` | Shared Claude plugin/commands/hooks/skills for this repo. | Keep shared config; local settings remain ignored. |
| `.context/` | Shared workflow context/preferences. | Keep tracked when it documents team/project workflow. |
| `.ccg/tasks/` | Task runner records. | Keep durable `plan.md`, `requirements.md`, and `task.json`; ignore turn logs and JSONL transcripts. |

## Local Or Generated Directories

| Path | Purpose | Cleanup rule |
|---|---|---|
| `.playwright-mcp/` | Browser automation logs/evidence. | Ignored; safe to delete when not actively debugging. |
| `.pytest_cache/`, `__pycache__/` | Python cache output. | Ignored; safe to delete. |
| `frontend/node_modules/` | Frontend dependencies. | Ignored; regenerate with package manager. |
| `logs/`, `*.log` | Local runtime logs. | Ignored; safe to delete after confirming no active debug need. |
| `.codegraph/*.db*` | Local CodeGraph index/runtime files. | Ignored; regenerate from local tooling. |

## Documentation Layout

Docs are grouped by purpose:

```text
docs/
  README.md           # documentation index
  architecture/       # architecture and schema references
  deployment/         # deployment guides
  features/           # feature plans and implementation notes
  audits/             # audit reports and verification plans
  evidence/           # fetched research, screenshots, and bulky evidence
```

Keep `docs/archive-manifest.md` at the docs root because it describes repository
cleanup history and restore locations across the whole project. Do not move docs
in the same change as business code refactors. Update links and
`docs/archive-manifest.md` when a document or evidence folder moves.
