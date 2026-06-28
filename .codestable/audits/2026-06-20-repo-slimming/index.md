---
doc_type: audit-index
status: implemented
audit_date: 2026-06-20
slug: repo-slimming
tags: [repo-hygiene, cleanup, slimming]
---

# Repo Slimming Audit

## Scope

Whole-repository hygiene pass for Crossroads Agent Café, focused on removable
dependencies, local runtime output, archived prototypes, generated verification
evidence, and tracked secret-risk files.

## Summary

The cleanup used the user-selected policy:较激进瘦身, secret/config files only
flagged as risk, and archived prototypes moved out of the active repository
without destroying their source.

## Findings

| ID | Type | Severity | Confidence | Finding | Action |
| --- | --- | --- | --- | --- | --- |
| 01 | maintainability | P1 | high | Root `node_modules/` was tracked, adding thousands of dependency files to Git. | Remove from Git and ignore. |
| 02 | maintainability | P1 | high | `_archive/` held inactive 2D/Colyseus code inside the active checkout. | Move source to external archive and add manifest. |
| 03 | maintainability | P2 | high | Local screenshots, Playwright traces, logs, and imagegen output polluted the source tree. | Move/delete generated evidence and ignore future output. |
| 04 | security | P1 | high | `.env` and MCP config files are tracked local configuration surfaces. | Do not modify in this pass; document owner follow-up. |

## Validation Targets

- `npm run build` in `frontend/`
- `python -m compileall app scripts tests`
- `python -m pytest -q`
- `python .codestable/tools/validate-yaml.py --dir .codestable/audits/2026-06-20-repo-slimming`
- HTTP smoke check for `http://127.0.0.1:8000/3d/scene` when a server is running
