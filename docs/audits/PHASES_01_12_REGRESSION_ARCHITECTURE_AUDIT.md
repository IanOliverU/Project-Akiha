# Phases 1–12 Regression and Architecture Audit

Date: 2026-10-06 (Asia/Taipei). Baseline commit:
`ea93f727aac5ee10331619c897bf919c4323aba2`, with existing uncommitted
Phase 13B work. This is a source and test audit of the working-tree snapshot,
not certification of a shipped binary or a completed Phase 13B audit.

## Milestone and boundaries

1. Inspect Phases 1–12 without changing runtime code, dependencies, assets,
   migrations, user data, or the existing Phase 13B changes.
2. Record evidence, severity, owner, verification, and disposition for each
   finding before beginning stabilization.
3. Stabilize only reproduced defects in a fixed file budget, with regression
   checks. Keep architecture moves, dependency upgrades, and release work in
   separately owned follow-ups.

Owners below are responsibility roles, not invented individual assignments.
High means potential private-data exposure or persistent upgrade damage;
Medium means a violated boundary or unreliable verification/operation; Low
means documentation drift. A confirmed risk is not evidence it occurred in a
released package.

## Read-only findings register

| ID | Category / severity | Finding and evidence | Owner | Disposition / acceptance check |
| --- | --- | --- | --- | --- |
| A01 | Architecture / Medium | `core/actions/executors.py` owns `os.startfile`, `subprocess.Popen`, and `ctypes.WinDLL` for Windows execution. This violates the explicit no-Windows-API core rule in `reference/CODEBASE_STRUCTURE.md`. | Action architecture maintainer | Deferred: move concrete OS adapters behind injected contracts in a separate change; preserve permission/confirmation tests and launch/close behavior. No evidence of a permission bypass follows from placement alone. |
| S01 | Security/privacy + packaging / High | `services/package_artifact.py` rejects `.db`, `.sqlite`, `.sqlite3` but misses SQLite `-wal`, `-shm`, and `-journal` companions. A synthetic `private.sqlite3-wal` carrying a private-content sentinel produced no finding. WAL/journals can contain database pages even if the main database is absent. | Release/privacy maintainer | Confirmed defect selected for stabilization: reject companions for all supported database extensions, case-insensitively, anywhere in the artifact; retain valid artifact acceptance. No real package leak was established. |
| U01 | Upgrade / High | `database/migrator.py` runs `executescript(sql)` without an explicit transaction and records the version afterward. Synthetic `CREATE TABLE; INSERT; INVALID SQL;` leaves the table behind and records no version. A retry can encounter partially applied schema. Current SQL files contain no BEGIN/COMMIT transaction wrapper. | Persistence maintainer | Confirmed defect selected for stabilization: transactionally bind each migration and its version receipt; prove rollback of DDL/data, retry success, and preservation of previously committed versions. |
| T01 | Tests / Medium | `tests/unit/database/test_migrator.py` checks fresh/idempotent migration and several upgrades, but its malformed SQL fails before valid DDL. It does not catch U01. `test_package_artifact.py` checks main database files but not companions, so it does not catch S01. | Persistence and release test maintainers | Selected for stabilization with behavior regressions for U01/S01; tests must fail against the baseline. |
| T02 | Disconnected upgrade verification / Medium | `scripts/smoke_packaged_app.ps1` starts fresh data, then reruns the same candidate on that new database for `-RunExistingDataPass`. This verifies restart, not upgrade from an older release schema. Its table set also omits `assistant_action_permissions` and `assistant_action_audit`, and does not assert ordered schema versions. | Release QA maintainer | Deferred: add a populated, isolated prior-version fixture, preserve its records/grants, and assert complete target schema. Never use the developer's live data. |
| P01 | Packaging/tooling safety / High | `scripts/build_akiha_pyinstaller.ps1` resolves unrestricted `WorkDir` and recursively removes it under `-Clean`, without proving containment or rejecting the project root. A mistaken root/parent argument can destroy unrelated working files. Static inspection only; no destructive reproduction was run. | Build tooling maintainer | Deferred to a dedicated script change: validate resolved cleanup targets before deletion, reject roots/ancestors, and test guards without deleting real directories. Do not exercise `-Clean` as part of this audit. |
| P02 | Packaging/upgrade reproducibility / Medium | `pyproject.toml` permits dependency ranges; no tracked lockfile was found. The PyInstaller report records Python and duration but not an exact installed dependency set or source revision. A later rebuild is not attributable to the same dependency/source snapshot. Dependency auditing and signing are explicitly deferred in the security review/backlog. | Release engineering maintainer | Deferred: record exact dependency inventory, source/tree identity and artifact digest; establish release constraints and dependency audit. No specific vulnerability or compatibility failure is asserted. |
| D01 | Outdated documentation / Low | `docs/README.md` says V0–V7 complete with V8 pending, while `roadmap/VOICE_INTELLIGENCE_V0_V8.md` explicitly closes V0–V8 and records V8 acceptance on 2026-08-13. | Documentation maintainer | Confirmed documentation correction selected for stabilization; align the index with the authoritative roadmap and retain historical records. |
| S02 | Privacy/error handling / Medium | Generic exception handlers in `integrations/gmail/provider.py:_poll_safely` and `integrations/discord/gateway.py:_run` use `logger.exception`, which emits arbitrary exception messages and tracebacks. This is inconsistent with a closed, sanitized provider-failure boundary if a transport embeds private data. | Integration/privacy maintainer | Confirmed logging risk, deferred: reproduce a private sentinel through each unexpected-error path, replace raw traceback logging with bounded reason codes, and retain health/reconnect behavior. Actual secret exposure was not established. |
| T03 | Regression gate / High | Full discovery terminates in `test_hosted_live_session_worker.test_tool_task_failure_stops_visibly_instead_of_stranding_turn`; the captured run exits `-1073740791` without a unittest summary. The same test and all six tests in its module pass in isolation. This establishes an order/environment-dependent gate failure, not its root cause. | Hosted-live runtime / Phase 13B maintainer | Deferred outside the stabilization budget: isolate preceding-test influence and ensure bounded thread cleanup; full discovery must complete normally. |
| T04 | Test/contract mismatch / Medium | Excluding the hosted-worker module allows 1,752 tests to finish, with five assertion failures in the one Phase 13B correction test `test_attack_paths_rejected_before_any_local_resolution`. The relative path `Downloads/Private/SECRET123.mp3` reaches the mocked resolver for four action kinds, contrary to the test's expectation. | Phase 13B action-contract maintainer | Deferred to the existing correction work: decide whether this relative descendant is valid under the intended contract and reconcile validation/test expectations. Do not infer an execution or permission bypass from a mocked resolver call. |

## Phase coverage and limits

The documentation index, ownership map, shared security/privacy records,
build/smoke scripts, migrator, artifact scanner, and test inventory were reviewed.
The full discovered source suite is the regression baseline, including current
Phase 13 tests; its result cannot isolate a clean Phase 12 release.

| Phase | Boundaries / regression evidence inspected | Audit result and remaining limit |
| --- | --- | --- |
| 1 Desktop pet | Animation bootstrap, pet window/renderer test inventory | Included in source suite; no new confirmed finding. Interactive Windows rendering was not reaccepted. |
| 2 Chat | Chat controller/failure tests; compatible-provider and transcript-export source | Included in source suite; no new confirmed chat defect. Live provider streaming not exercised. |
| 3 Memory | Memory repositories, extraction/context tests; ordered migrations | U01 applies to persistence upgrades. No real conversation/memory data inspected. |
| 4 Behavior | Activity/mood/proactive/notification-policy tests | Included in source suite; no new confirmed policy defect. Timing and presentation were not manually tested. |
| 5 Polish | Tray, Settings, privacy-notice and history test inventory | Included in source suite; interactive accessibility/tray acceptance not repeated. |
| 6 Packaging | Build scripts, artifact deny scan, migrator and release docs | S01, U01, T01, T02, P01, P02. No rebuild, clean operation, or package launch performed. |
| 7 Voice | Voice/session worker/controller tests and authoritative V0–V8 record | D01. Microphone, model runtimes and live speech were not exercised. |
| 8 Actions | Core executor/platform implementation and documented ownership; permission/action tests | A01. Existing Phase 13B action changes preserved; their independent review remains separate. |
| 9 Pet simulation | Pet state/reward repository and rules/service tests | Included in source suite; U01 applies to upgrades. No live state reset. |
| 10 Shop/visual | Shop/appearance repository and service test inventory | Included in source suite; U01 applies to upgrades. No artwork or catalog changes. |
| 11 Integrations | Gmail/Discord failure handlers; hashed receipt and provider test inventory | S02. No account authentication, polling, or messages sent. |
| 12 Runtime/notifications | Single-instance, notification repository/coordinator and provider-health tests; phase closure record | Included in source suite; T02 limits packaged upgrade evidence. Historical owner acceptance remains historical. |

No automatic import-boundary gate was found in the reviewed checks; Ruff's
enabled rules do not enforce the documented layer dependencies. An architecture
gate should accompany A01's eventual move. Passing unit tests alone does not
close deferred release, security, architecture, or manual verification findings.

## Bounded stabilization contract

Selected IDs: S01, U01, T01, D01 only. File budget: migrator, artifact
validator, their two existing test modules, documentation index, this audit
and its stabilization record. No executor relocation, dependency changes,
new SQL migration, Phase 13B edits, live user-data access, or release rebuild.

Exit checks: baseline source result recorded; new tests reproduce the original
defects; focused checks pass after fixes; full source suite and scoped
Ruff/Black pass; final diff stays inside the file budget. Deferred findings
remain open with their owners and acceptance checks above. Milestone release
sign-off remains open until deferred high-severity release risks are addressed
and a candidate has appropriate packaged verification.

## Recorded outcome

Read-only audit complete for the stated source-review scope: 11 findings.
The selected bounded fixes are implemented; see
[STABILIZATION_2026-10-06.md](STABILIZATION_2026-10-06.md) for exact changes,
checks and remaining gate failures. The milestone is **not release-cleared**:
the whole-suite gate remains unsuccessful, and deferred findings stay open.
