---
doc_type: issue-fix
slug: customer-hall-roam
severity: medium
status: fixed
tags:
  - frontend
  - 3d-scene
  - movement
  - customer
created_at: 2026-06-20
---

# customer-hall-roam Fix Note

## Symptom

3D cafe visitors (`role=customer`, label "访客") kept roaming across the whole hall after arriving, even when there was no backend visualization event directing them to move.

## Root Cause

`frontend/src/sim/tick.ts` ran the autonomous idle `SOCIAL_ROAM_PROBABILITY` branch for every non-working, non-error, non-away agent. Customers were not excluded, so every frame had a chance to send them to random social furniture or global `ROAM_POINTS`.

At ~60fps, `SOCIAL_ROAM_PROBABILITY = 0.005` is enough to make idle visitors look like they are wandering aimlessly.

## Fix

Added a customer guard in `settleIdle()`:

- `customer` agents keep responding to backend-directed movement events (`enter_scene`, `walk_to_counter`, `walk_to_table`, `leave_scene`).
- Once a customer reaches the target and has no path, it settles to `standing`.
- Customers no longer enter the staff social-roam / away-furniture loop.
- Staff roles keep the existing autonomous social-roam behavior.

Changed file:

- `frontend/src/sim/tick.ts`

## Verification

```powershell
cd frontend
npm run build
```

Result: `tsc --noEmit && vite build` passed. Vite still reports the existing large-chunk warning.

Additional recheck:

```powershell
git diff --check -- frontend/src/sim/tick.ts app/static/3d/index.html
node -e "const fs=require('fs'); const s=fs.readFileSync('frontend/src/sim/tick.ts','utf8'); const guard=s.indexOf('if (isCustomerAgent(agent))'); const roam=s.indexOf('Math.random() < SOCIAL_ROAM_PROBABILITY'); if (guard < 0 || roam < 0 || guard > roam) { console.error({guard,roam}); process.exit(1); } console.log('customer guard precedes social roam branch');"
```

Result: whitespace check passed, and the customer guard is confirmed to run before the social-roam branch.

Dynamic behavior recheck:

- Bundled the current TypeScript sources in memory with `esbuild`.
- Created one idle `customer` and one idle `waiter` in the same tick simulation.
- Forced `Math.random()` to return `0`, which guarantees the autonomous social-roam branch would trigger if reachable.

Result:

```json
{
  "customer": {
    "state": "standing",
    "pathLength": 0,
    "targetX": 400,
    "targetY": 400
  },
  "staff": {
    "state": "walking",
    "pathLength": 12,
    "targetX": 800,
    "targetY": 200
  }
}
```

This confirms customers no longer receive an autonomous roam path, while the staff control case still keeps the existing social-roam behavior.
