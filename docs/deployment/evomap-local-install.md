# EvoMap Local Tooling

This project does not keep a root Node.js package for EvoMap tooling. The active
frontend package lives under `frontend/`; root-level `package.json`,
`package-lock.json`, and `node_modules/` are intentionally ignored as local
tooling artifacts.

## Usage

Run EvoMap/Evolver commands on demand instead of installing them globally:

```powershell
cd <repo-root>
npx --yes @evomap/evolver@1.89.14 --help
```

If a task needs a project-local temporary install, keep it untracked:

```powershell
cd <repo-root>
npm install --no-save @evomap/evolver@1.89.14
.\node_modules\.bin\evolver.cmd --help
```

## Cleanup Rules

- Do not commit root-level `node_modules/`.
- Do not commit root-level `package.json` or `package-lock.json` unless the
  repository intentionally gains a root Node package.
- Do not run setup commands that write global editor or agent configuration
  under the user home directory, such as `~/.cursor/`, `~/.claude/`, or similar
  tool-specific folders.
- Keep EvoMap node secrets in local environment files or the platform secret
  store. Do not copy credentials into docs, scripts, package files, or logs.
