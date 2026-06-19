---
description: Review Evolver's pending evolved changes, then approve (solidify) or reject (roll back).
argument-hint: "[--approve | --reject]"
allowed-tools: Bash
---

Review the changes Evolver currently has **pending solidify** in this repository.

1. First show the user what is pending — run `git status --short` and `git diff` (or `git diff HEAD`) so they can see the actual proposed edits.
2. Resolve the project-local CLI:

```bash
EVOLVER="./node_modules/.bin/evolver"
[ -f "$EVOLVER" ] || EVOLVER="./node_modules/.bin/evolver.cmd"
[ -f "$EVOLVER" ] || { echo "project-local Evolver CLI missing; restore node_modules from this repo checkout."; exit 1; }
```

3. Then act on the user's intent:
   - If the user passed `--approve` (or asked to accept): run `$EVOLVER review --approve` to solidify.
   - If the user passed `--reject` (or asked to discard): run `$EVOLVER review --reject` to roll back.
   - If no flag was given via `$ARGUMENTS`, summarize the pending diff and **ask the user** whether to approve or reject before running anything.

Report the final state (solidified / rolled back) and the resulting git status.
