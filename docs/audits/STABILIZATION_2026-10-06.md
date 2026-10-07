# Phases 1–12 bounded stabilization — 2026-10-06

Scope fixed before runtime edits in the
[audit register](PHASES_01_12_REGRESSION_ARCHITECTURE_AUDIT.md).

## Changes

- U01: each SQL migration starts an explicit transaction inside `executescript`;
  its schema-version receipt commits with the schema/data changes. Failure
  explicitly rolls back. Previously successful migrations remain committed.
- S01: the package validator also rejects case-insensitive `.db`, `.sqlite`,
  `.sqlite3` companions with `-wal`, `-shm`, or `-journal`, at any nested path.
- T01: regressions verify rollback of valid DDL and data preceding invalid SQL,
  preservation of existing data/version, successful retry and idempotence;
  artifact tests exercise all nine companion combinations without a main DB.
- D01: the documentation index now reflects the authoritative V0–V8 closure
  and links this audit.

Seven files changed/added by this pass: the migrator, artifact validator,
their two existing test modules, `docs/README.md`, the audit register and this
record. Existing Phase 13B edits were preserved. No new migration, dependency
update, architecture relocation, package build, or live-data mutation occurred.
Local verification logs are under `artifacts/audit-phases-01-12/` (ignored
artifacts, not release evidence).

## Verification

Environment: workspace `.venv313/Scripts/python.exe`, bytecode disabled.

| Check | Result |
| --- | --- |
| Baseline full discovery, before stabilization | Process exited abnormally without a unittest summary; no passing baseline claimed. |
| New regression tests using the two original modules from `git show HEAD:<path>` loaded in memory | Both fail as expected: one migration assertion and nine companion subtest assertions. No checkout or source overwrite. |
| `python -B -m unittest tests.unit.database.test_migrator tests.unit.services.test_package_artifact` | 18 tests pass after stabilization. |
| Ruff and Black check on the four changed Python files | Pass. |
| `git diff --check` | Pass. |
| Full verbose discovery after stabilization | Abnormal exit `-1073740791` during hosted-worker test; T03. |
| Hosted-worker module in isolation | All 6 tests pass; the failing-position test also passes alone. |
| Full discovery excluding that module | 1,752 tests finish, 3 skipped, 5 assertion failures, all in one Phase 13B correction test; T04. |

The selected fixes pass their relevant checks, but the global regression gate
is **not green**. No release approval or claim of Phase 13B completion follows.

## Remaining ownership and risks

S01, U01, T01 and D01 are addressed in source. A01, T02, P01, P02, S02,
T03 and T04 remain open with acceptance checks in the audit register.

The migrator now owns transaction control. Future bundled SQL must not commit,
roll back, or start a transaction itself; current migrations were checked and
contain no such statements. No attempt was made to repair a database already
partially migrated by an older build. Name-based package scanning also remains
a denylist, not a content scanner for arbitrarily renamed private data.

Before distribution, resolve the unsafe clean-path finding and the unsuccessful
whole-suite gate, then verify a fresh candidate and a populated prior-schema
upgrade fixture. Keep Phase 13B corrections and larger architecture changes
in separately reviewable work.
