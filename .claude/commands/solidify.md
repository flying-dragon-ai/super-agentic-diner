---
description: Solidify the current working changes into a durable Evolver gene/capsule (with rollback safety).
argument-hint: "[--dry-run] [--intent=repair|optimize|innovate] [--summary=\"...\"]"
allowed-tools: Bash
---

Solidify the current working-tree changes into a durable Evolver asset.

1. Ensure we're in a git repo and show `git diff --stat` so the user sees what will be captured.
2. Resolve the project-local CLI and run solidify with the user's flags:

```bash
EVOLVER="./node_modules/.bin/evolver"
[ -f "$EVOLVER" ] || EVOLVER="./node_modules/.bin/evolver.cmd"
[ -f "$EVOLVER" ] || { echo "project-local Evolver CLI missing; restore node_modules from this repo checkout."; exit 1; }
$EVOLVER solidify $ARGUMENTS
```

3. If the user did not provide `--summary`, infer a concise one-line summary of the change from the diff and pass it as `--summary="..."`.
4. Report the gene/capsule that was created or updated, and whether a rollback point was recorded.

Tip: pass `--dry-run` first to preview without writing.
