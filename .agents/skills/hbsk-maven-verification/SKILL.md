---
name: hbsk-maven-verification
description: Use for HBSK verification planning and troubleshooting when running Maven tests/builds, OpenSpec validation, PowerShell commands, or repo searches; applies to repeated issues with skipped tests, quoted `-Dtest` properties, upstream reactor failures, ignored `openspec/`, and exact evidence reporting.
---

# HBSK Maven Verification

Use this skill in `D:/codingProjects/JAVA/HBSK` when a task needs reliable verification commands or when Maven, PowerShell, `rg`, or OpenSpec validation behaves unexpectedly.

## Evidence Basis

This workflow comes from repeated May 2026 HBSK work where verification failed or was ambiguous because of:

- root Maven defaults skipping tests;
- PowerShell parsing dotted or comma-separated Maven properties;
- broad reactor runs failing in unrelated upstream modules;
- ignored `openspec/` paths hiding doc changes;
- quote-heavy `rg` searches and wildcard path arguments failing on Windows.

## Command Selection

1. Identify the touched module and nearest tests before running Maven.
2. Prefer focused module tests over broad reactor tests.
3. If dependencies are missing, populate them with an install that does not compile tests:

```powershell
mvn -pl <module-path> -am "-Dmaven.test.skip=true" install
```

4. Run actual tests with `-DskipTests=false`:

```powershell
mvn -pl <module-path> "-Dtest=<TestClass1>,<TestClass2>" -DskipTests=false test
```

5. If upstream modules reject the test pattern, add:

```powershell
"-Dsurefire.failIfNoSpecifiedTests=false"
```

6. If a broad `-am test` fails before reaching the target module, record the upstream failure and switch to the narrowest target-module command that still verifies the change.

## Known HBSK Patterns

- A Maven `BUILD SUCCESS` is not proof when output says `Tests are skipped`.
- In PowerShell, quote dotted Maven properties such as `"-Dmaven.test.skip=true"` and `"-Dsurefire.failIfNoSpecifiedTests=false"`.
- In PowerShell, quote comma-separated `-Dtest` values: `"-Dtest=ATest,BTest"`.
- Avoid broad `-am test` unless the blast radius requires it. Upstream modules may fail with unrelated Surefire or test compile issues.
- For `openspec/`, normal `git status`, `git diff`, or default `rg` may miss files if the directory is ignored. Use direct reads or `rg --no-ignore`.
- For wildcard-like path searches, prefer `rg --files | rg "pattern"` or `rg -g "Pattern*.java"` over shell-expanded wildcard path literals.

## Reusable Commands

Core DMS focused tests:

```powershell
mvn -pl hbsk-modules/hbsk-core/core-dms "-Dtest=ExportEmptyPassServiceImplTest,ExportEmptyPassMapperContractTest" -DskipTests=false test
```

Core Domain plus Core DMS when DTO/domain changes are involved:

```powershell
mvn -pl hbsk-modules/hbsk-core/core-domain,hbsk-modules/hbsk-core/core-dms -DskipTests=false -DfailIfNoTests=false "-Dsurefire.failIfNoSpecifiedTests=false" "-Dtest=ExportEmptyPassMapperContractTest,ExportEmptyPassServiceImplTest" test
```

Datasource audit focused tests:

```powershell
mvn -pl hbsk-starter/hbsk-starter-datasource test "-DskipTests=false" "-Dtest=AnnotatedAuditTableDefinitionTest,AuditedTableAutoConfigurationTest,AuditedTableScannerTest,AuditCompanionSampleGeneratorTest,SnapshotServiceTest"
```

Starter log module tests:

```powershell
mvn -pl hbsk-starter/hbsk-starter-log -DskipTests=false test
```

OpenSpec strict validation:

```powershell
openspec validate <change> --strict
```

## Evidence Reporting

When closing a task:

- state the exact command;
- state whether tests actually ran;
- include test counts when available;
- separate unrelated upstream failures from task-owned failures;
- do not invent exit codes or pass/fail status;
- do not run `git add`, commit, or push unless explicitly asked.
