---
doc_type: audit-finding
status: open
severity: P1
nature: security
confidence: high
tags: [secrets, env, mcp]
---

# Tracked Local Configuration Surfaces Remain

## Evidence

`.env`, `.mcp.json`, and `.mcp.json.backup` are tracked local configuration
files. Their contents were not printed or modified during this cleanup.

## Impact

Tracked local config files are a standing leak risk for database passwords,
Redis passwords, API keys, node secrets, and full connection strings.

## Action

Per user instruction, this pass only flags the risk. A future security hygiene
task should move real local values out of Git while preserving `.env.example`
and wrapper scripts.
