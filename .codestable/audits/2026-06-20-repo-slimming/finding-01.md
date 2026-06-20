---
doc_type: audit-finding
status: implemented
severity: P1
nature: maintainability
confidence: high
tags: [node, dependencies, git]
---

# Root node_modules Was Tracked

## Evidence

`git ls-files node_modules` reported `3109` tracked dependency files, while the
root package metadata is already sufficient to restore dependencies.

## Impact

Large dependency trees make reviews noisy, slow down Git operations, and create
unnecessary merge conflicts.

## Action

Remove `node_modules/` from Git and add a root ignore rule.
