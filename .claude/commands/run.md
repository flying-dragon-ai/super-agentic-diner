---
description: Run one Evolver self-evolution cycle on the current repo (collect signals → select/mutate genes → propose changes).
argument-hint: "[--loop] [--dry-run] [--strategy=balanced|innovate|harden|repair-only]"
allowed-tools: Bash
---

Run an Evolver evolution cycle in the **current git repository**.

Steps:
1. Confirm we're in a git repo (`git rev-parse --is-inside-work-tree`). If not, tell the user Evolver requires git and stop.
2. Resolve the project-local CLI and run it, passing through the user's flags. Execute:

```bash
EVOLVER="./node_modules/.bin/evolver"
[ -f "$EVOLVER" ] || EVOLVER="./node_modules/.bin/evolver.cmd"
[ -f "$EVOLVER" ] || { echo "project-local Evolver CLI missing; restore node_modules from this repo checkout."; exit 1; }
EVOLVE_STRATEGY="${EVOLVE_STRATEGY:-balanced}" $EVOLVER run $ARGUMENTS
```

3. Summarize what changed: which signals were collected, which gene was selected/mutated, and whether any changes are now **pending solidify**. If changes are pending, remind the user they can inspect and accept them with `/evolver:review` (or roll back with `/evolver:review --reject`).

Do not auto-approve pending changes — leave that to the user via `/evolver:review`.
