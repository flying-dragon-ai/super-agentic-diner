---
doc_type: repo-archive-manifest
status: active
updated_at: 2026-06-28
---

# Archive Manifest

This repository keeps active Crossroads Agent Café source in the root `app/`,
`frontend/`, `.agents/`, `scripts/`, and `tests/` trees.

The former in-repository `_archive/` tree was moved out of the active checkout
during the 2026-06-20 repo slimming pass (re-removed 2026-06-28 after a merge had re-introduced `_archive/` into the active checkout; the external archive below remains the authoritative restore source):

```text
D:\temp\EVOMAP\coffee-ai-boss-archive\2026-06-20-repo-slimming\
```

## Moved Content

- `_archive/colyseus-server/`: archived Colyseus pixel-room prototype.
- `_archive/2d-legacy/`: archived 2D HTML chat page and matching local audio.
- `.artifacts/`: local screenshots and smoke-test helpers from prior UI/API
  verification runs.
- `.playwright-mcp/`: local Playwright MCP screenshots, page snapshots, and
  console logs.
- `output/imagegen/`: generated image experiments and prompts.
- `logs/` plus root `server.*.log`: local run logs.
- Root UI screenshots such as `cafe-redesign*.png` and `topbar-fix-verify.png`.
- `docs/m1.mp3` and `docs/m2.mp3`: duplicate audio copies removed from docs; active copies remain
  under `frontend/public/sounds/` and `app/static/3d/sounds/`.
- Top-level docs were reorganized on 2026-06-28:
  - deployment guides moved to `docs/deployment/`.
  - architecture/schema references moved to `docs/architecture/`.
  - feature plans moved to `docs/features/`.
  - audit/check plans moved to `docs/audits/`.
  - fetched research and visual evidence moved to `docs/evidence/`.
  - duplicate 3D editor docs `docs/3D编辑器保存机制对齐.md` and
    `docs/3D编辑器完整度对齐.md` had identical content and were collapsed into
    `docs/features/3d-editor-completeness-alignment.md`.

Ignored dependency/build output such as `node_modules/` and `dist/` was not kept
as active source; restore it from lockfiles if the archived prototype is revived.

## Restore Notes

- To restore the Colyseus prototype, copy the external
  `_archive/colyseus-server/` directory back to repository root as
  `colyseus-server/`, then run its package install/build steps.
- To inspect the old 2D page, open the archived `2d-legacy/index.html` from the
  external archive path above.
- To inspect old verification evidence, browse the matching external
  `.artifacts/`, `.playwright-mcp/`, `output/imagegen/`, or `logs/` directory.
- The active UI is the React/Vite 3D frontend served from `app/static/3d/`.

## Security Note

Local secret-bearing files such as `.env`, `.mcp.json`, and `.mcp.json.backup`
were intentionally not modified by this cleanup. They remain a follow-up
repository hygiene risk if they are tracked in Git.
