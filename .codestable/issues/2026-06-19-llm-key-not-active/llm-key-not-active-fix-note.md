---
doc_type: issue-fix
status: completed
severity: medium
tags:
  - llm
  - configuration
  - runtime-status
---

# LLM Key Not Active Fix Note

## Problem

The application reported `llm_active=false` even though the user expected a real LLM key to be configured. The runtime chain showed:

- `.env` contained `LLM_API_KEY`, but its value was empty.
- The current Python process had no `LLM_API_KEY` or `OPENAI_API_KEY` in the process environment.
- `/status` returned `llm_active=false`.
- `has_real_key()` only checked `settings.llm_api_key`, so provider-specific aliases such as `DEEPSEEK_API_KEY` or `OPENAI_API_KEY` would not activate the LLM.

## Fix

- Added safe LLM key resolution in `app/config.py`.
  - Supports `LLM_API_KEY`, `DEEPSEEK_API_KEY`, and `OPENAI_API_KEY`.
  - Exposes `effective_llm_api_key`, `llm_api_key_source`, and `llm_status_reason`.
  - Treats blank and placeholder values as inactive.
- Updated `app/llm/client.py`.
  - `has_real_key()` now uses `settings.effective_llm_api_key`.
  - Authorization now uses the resolved effective key.
- Updated `/status` in `app/main.py`.
  - Returns non-secret diagnostics: `llm_key_source`, `llm_status_reason`, `llm_base_url`, and `llm_model`.
- Updated `.env.example`.
  - Documents that one of `LLM_API_KEY`, `DEEPSEEK_API_KEY`, or `OPENAI_API_KEY` must be filled.
- Added `tests/test_llm_configuration.py`.
  - Covers blank keys, provider aliases, precedence, and placeholder rejection.

## Verification

- `python -m pytest -q` passed: 8 tests.
- `python -m compileall app scripts tests` passed.
- Restarted the local server on port 8000.
- Runtime `/status` now returns diagnostic fields. After configuring the local `.env`, the active runtime on port 8001 reports:
  - `llm_active=true`
  - `llm_key_source=LLM_API_KEY`
  - `llm_status_reason=configured`
  - `llm_model=evomap-gemini-3.1-pro-preview`
- A minimal real LLM request returned `OK`.

The code path and provider call are both verified.

## Remaining Action

Port 8000 is still occupied by stale Windows TCP listener entries whose PIDs are not visible to `taskkill`. The verified current server is running on port 8001. If port 8000 must be reclaimed, restart the stale process owner or reboot the local dev environment.
