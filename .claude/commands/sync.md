---
description: Sync evolution assets (genes/capsules) between the local store and the EvoMap Hub.
argument-hint: "[--scope=all|purchased|published] [--type=Gene|Capsule] [--export=<path.gepx>] [--dry-run]"
allowed-tools: Bash
---

Sync Evolver assets with the EvoMap Hub.

```bash
EVOLVER="./node_modules/.bin/evolver"
[ -f "$EVOLVER" ] || EVOLVER="./node_modules/.bin/evolver.cmd"
[ -f "$EVOLVER" ] || { echo "project-local Evolver CLI missing; restore node_modules from this repo checkout."; exit 1; }
$EVOLVER sync $ARGUMENTS
```

After it runs, summarize: how many assets were pulled/updated, any local-only (unpublished) assets it listed, and — if `--export` was given — where the `.gepx` archive was written.

If it reports the node identity or Hub credentials are missing, point the user to `/evolver:status` and the README's *EvoMap Hub* section to diagnose.
