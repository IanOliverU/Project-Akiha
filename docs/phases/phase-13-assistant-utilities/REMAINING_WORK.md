# Phase 13 continuous completion task — authorized 2026-10-09

The owner authorized one continuous task covering 13D through 13I, including
13E–13H, automated verification, review/corrections, cleanup safety, outstanding
shutdown/package checks and a fresh consolidated candidate. Final owner
acceptance stays pending the complete numbered manual checklist. No push is
authorized by this task. This authorization does not turn unperformed gates into
passes or waive the documented exclusions.

## Authoritative remaining specifications

This checkout has no separate PHASE13D.md through PHASE13I.md. Their maintained
scope and acceptance criteria are the 13D–13I sections, architecture/ownership
record and exit criteria in [README.md](README.md). The relevant existing
context is Phase 8's typed action/default-deny/approved-root contract, Phase 12's
single-instance/provider-health/inbox/presentation architecture, the shared
LOCAL_DATA_PRIVACY, SECURITY_REVIEW and CODEBASE_STRUCTURE records, Phase 13A
utility/clock contracts, 13B safeguards/accepted closure and 13C implementation
and review records. These remain authoritative; no new scope is invented to
replace nonexistent phase files.

## Dependency order and tracked work

1. Finish 13C: normal Windows execution of the corrected six composed tests,
   required full single-process discovery, ten historical Qt pairs, source smoke
   and reconciliation of inventory/results. Preserve owner timer-behavior
   acceptance. Do not mark 13C complete on discovery counts or old 1878 totals.
2. 13D: one-shot reminders with explicit local date/time/timezone, DST
   ambiguity/nonexistence clarification, list/cancel/snooze, one shared schedule
   owner, bounded missed policy and minimal persistence/atomic receipts through
   the existing migrator. No recurring reminders/calendar sync.
3. 13E: provider-neutral read-only current weather/forecast/official alerts from
   an explicitly configured location; source/freshness/uncertainty and bounded
   offline/auth/network failures. No arbitrary browsing/provider URLs, action
   authority, implicit location collection or automatic long-term memory.
4. 13F: approved-root contextual discovery/opening with current permissions,
   ambiguity choices, revocation/ownership checks and traversal/symlink/reparse
   tests. No file-content ingestion, mutation or arbitrary provider paths.
5. 13G: versioned manifest and explicit selection of conversations/memories,
   trusted-local destination and current confirmation, bounded atomic writing
   and sanitized failure reporting. Exclude credentials/tokens/raw provider
   responses/logs/private notification receipts/local voice references. No
   restore/import/cloud backup.
6. 13H: focused schedule/location/health/retention/export controls on existing
   Settings/health/inbox surfaces; sanitized bounded diagnostics/failure recovery;
   regression/privacy evidence for chat, voice, pet, memory, Gmail, Discord and
   startup. No second command/permission/scheduler/voice/presentation framework.
7. 13I: complete quality/migration/restart/timezone/offline/privacy and independent
   review gates; resolved cleanup guard; graceful pending-clarification shutdown;
   fresh consolidated PyInstaller candidate after source gates; package privacy,
   dependency completeness, single-instance/provider/voice/shutdown verification.
   Produce one numbered owner checklist with exact supported commands and
   expected results for every retained requirement. Owner confirmation that
   every checklist item passed closes Phase 13 only after automated/review gates
   pass. No installer/signing/auto-update/public distribution expansion.

13E–13H are retained in the task, not dropped or independently deferred. The
owner's instruction to finish 13C verification **first**, then implement in
dependency order, remains the boundary before starting 13D–13I.

## Historical prerequisite blocker (superseded by the passing runs below)

No new unrestricted 13C run is present locally; existing generated verification
folders contain inventory-only results. This session independently reproves
QLocalServer(UserAccessOption) access denied and default Windows asyncio stuck
in socket.accept / fallback socketpair / Proactor self-pipe before utility code.
The required full discovery attempt after the cleanup tests were added blocked
and was interrupted with exit 1 and no final totals. No full pass, graceful
shutdown or package pass is inferred. No IPC/GC/test/loop protections are bypassed.

Run in normal Windows PowerShell:

```powershell
Set-Location 'C:\Users\MY PC\Desktop\Project Akiha'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify_phase13c.ps1
```

The script now also captures `cleanup-guard.log` and its exit code. Return the
entire printed folder, including gate-results.json, inventory.json, file-hashes,
HEAD/status and all log/exit-code files. Current inventory is **1924** unique
tests (1917 plus seven cleanup-guard tests); timer selection remains 38. The
inventory must be reconciled dynamically when subsequent tests are added.
Source smoke's forced-stop field is not graceful-shutdown proof.

## Historical cleanup correction (verification now passed)

The audited baseline accepts WorkDir `.` as the project root, then recursively
removes it under Clean. A safe baseline probe executed only its resolver and
confirmed that mapping; no destructive baseline/clean build was executed.

`scripts/build_path_guard.ps1` validates resolved paths before Python/preflight
or directory creation in the PyInstaller builder. Work/output must be strict,
non-overlapping descendants of project/dist. Roots/parents/source/prefix
collisions, wildcard/device/UNC/drive-relative/dot-segment/ambiguous trailing
forms, file ancestors and reparse ancestors reject. Before either Clean delete,
both final targets and their trees are checked. Shallow enumeration rejects
reparse children before descending. Literal-path deletion remains in one shell.
This intentionally restricts custom output/work locations to project/dist.

Seven enabled Windows regressions execute actual PowerShell guard functions and
the actual builder's root-rejection branch. They do not perform a clean build or
delete real developer directories. **Six passed; one failed (exit 1)** because
the session denied creation of the junction fixture, before the guard assertions
could execute. The junction test is retained and not skipped or weakened.
PowerShell syntax, Ruff and formatting pass. Full cleanup-guard verification
still requires all seven tests passing in the normal Windows environment.
**No clean packaging until that evidence is reviewed.**

Modified/new files for this prerequisite: `scripts/build_akiha_pyinstaller.ps1`,
`scripts/build_path_guard.ps1`, `tests/unit/services/test_build_cleanup_guard.py`,
and the added gate in `scripts/verify_phase13c.ps1`. Log:
`dist/phase13-cleanup-guard-tests.log` (7 tests, 2.387 s, failures=1, exit 1).
No runtime utility implementation, phase completion, package, owner acceptance
or push occurred in this prerequisite pass. Existing accepted functionality and
the recorded shutdown/package obligations remain intact.

## Reviewed normal Windows run — 2026-10-09

The owner's `phase13c-verification-20261009-025651-5d46ef` evidence supersedes
the guard restriction above: all seven guard tests, including junction creation
and rejection assertions, passed with exit 0. Captured guard hashes match the
reviewed tree. The cleanup prerequisite is verified; clean packaging still
waits for accepted source gates. Ten historical Qt pairs also passed.

Full discovery ran 1924 tests with two failures and exit 1; timer selection ran
38 with one failure and exit 1. Reproduced and corrected: timer-label echo in
the UI transcript (production composer now omits typed timer action echo), and
missing-runtime test discovery escaping its fixture into the installed checkout
(fixture now contains the entire four-ancestor search). See PHASE13C.md for
exact evidence and commands. Available post-correction tests: 43 pass; Ruff,
Black API, compilation, static boundaries and diff check pass. The strengthened
composed tests and required full discovery need the same normal Windows script
rerun. No tests were skipped, disabled or weakened; inventory remains 1924.

Source smoke exited 0 but forced termination, so pending-clarification graceful
shutdown and package checks remain outstanding. Owner timer-behavior acceptance
and continuous 13D–13I authorization are preserved. Implementation of the
dependent phases resumes after the corrected required 13C gates pass; no
additional authorization is required.

## Current status — consolidated implementation and verification, 2026-10-09

The corrected owner folder `phase13c-verification-20261009-030430-a61707`
passed all gates with 1924 tests, zero skips and matching hashes; Phase 13C
verification was completed before continuing. The current runner can execute
normal Windows IPC/asyncio and junction tests through the authorized Windows
execution tool. The historical restrictions above are no longer blockers.

13D–13H are implemented and source-verified without dropping a subphase.
The final single-process suite passes **1990 tests, no skips, exit 0**;
64 new utility/composition tests pass independently; ten historical Qt pairs,
all seven guard tests, Ruff/Black, compilation/static boundaries, security,
database/shutdown selections, source smoke and diff checks pass. Independent
production-service probes also pass. No tests/IPC/GC protections were weakened.

The verified guard prerequisite was preserved before the clean consolidated
candidate at `dist/phase13-consolidated-20261009/Akiha`. Artifact/privacy and
GUI subsystem validation pass. Graceful pending-clarification shutdown is now
proved in source and package with fresh isolated default profiles and normal
process exit 0. Live configured sessions remain owner checks. The legacy
CloseMainWindow smoke still forced termination and is used only for startup,
database and log evidence, not as graceful proof.

See [the consolidated evidence/manifest](CONSOLIDATED_VERIFICATION.md) and
[one complete numbered owner checklist](OWNER_CHECKLIST.md). 13I remains active
pending consolidated owner testing. No final owner acceptance, Phase 13 closure,
commit or push has been recorded. Optional real account/microphone/network
verification is not inferred from mock/offline runtime tests.

## Owner acceptance and closure ? 2026-10-13

The owner confirmed the entire Phase 13 looks good, accepted the native UI
candidate, requested removal of chat message highlighting, and explicitly
authorized committing and pushing all reviewed changes since Phase 13C.
Phase 13A?13I is complete. No subsequent phase is activated by this record.
Owner testing is owner-reported; it is not relabeled as automated live-provider
evidence. Historical environment failures remain documented and do not override
the later passing gates. Generated builds, verification artifacts and private
data are excluded from the source checkpoint. The clean-build guard remains
mandatory; recurrence, restore/import and other explicit exclusions remain out
of scope.

## Owner acceptance and closure - 2026-10-13

The owner confirmed the entire Phase 13 looks good, accepted the native UI
candidate, requested removal of chat message highlighting, and explicitly
authorized committing and pushing all reviewed changes since Phase 13C.
Phase 13A through 13I is complete. No subsequent phase is activated here.
Owner testing is owner-reported, not automated live-provider evidence. Historical
environment failures remain documented alongside later passing gates. Generated
builds, verification artifacts and private data are excluded from the checkpoint.
The clean-build guard remains mandatory; recurrence, restore/import and all
other explicit exclusions remain out of scope.

## Current owner instruction - 2026-10-13 exact-HEAD revalidation

After pushing 88a7e6b, the owner requested Phase 13 remain pending until the
required exact-revision checks pass. Earlier acceptance/closure is preserved
as history; it does not close this renewed candidate gate. See
CURRENT_HEAD_VERIFICATION.md and OWNER_CHECKLIST_CURRENT_HEAD.md. No additional
features, implementation changes, commit or push are part of this reconciliation.
