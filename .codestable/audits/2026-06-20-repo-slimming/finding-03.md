---
doc_type: audit-finding
status: implemented
severity: P2
nature: maintainability
confidence: high
tags: [artifacts, logs, screenshots]
---

# Runtime Evidence Polluted Source Tree

## Evidence

Tracked or untracked runtime evidence existed under `.artifacts/`,
`.playwright-mcp/`, `output/imagegen/`, root screenshots, and server log files.

## Impact

Generated evidence is useful during debugging but should not remain mixed with
source unless promoted to durable documentation or tests.

## Action

Move recoverable evidence to the external archive, remove it from active source,
and ignore future generated output.
