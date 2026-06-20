---
doc_type: audit-finding
status: implemented
severity: P1
nature: maintainability
confidence: high
tags: [archive, legacy-ui, colyseus]
---

# Archived Prototypes Lived In Active Source Tree

## Evidence

Project docs marked `_archive/colyseus-server/` and `_archive/2d-legacy/` as
inactive historical implementations, while active runtime is the 3D frontend and
FastAPI visualization WebSocket.

## Impact

Keeping inactive prototypes in the main checkout inflates project size and
invites accidental edits to abandoned code.

## Action

Copy archive source to an external recoverable archive path, remove `_archive/`
from the active repository, and add `docs/archive-manifest.md`.
