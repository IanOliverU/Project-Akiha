# Phase 13C: One-shot timers

Status: complete, 2026-10-09. Owner timer-behavior acceptance, bounded review,
correction verification and unrestricted single-process gates are recorded below.
Graceful pending-clarification shutdown and packaged verification remain tracked
for the authorized consolidated 13I gate; timer completion does not waive them.

## Required context and existing boundaries

Reviewed the maintained Phase 13 plan/13A architecture record, Phase 13B closing
record and bounded review, Phase 8 action contract, codebase structure, security
and privacy references, and existing `core/utilities/contracts.py` and `clock.py`.

Use the existing ActionRequest/ActionRegistry, action service, scoped policy,
clarification/confirmation owner, EventBus, Notification Center and presentation
arbitration. Use one schedule-service owner; do not create separate scheduler,
permission, notification or voice systems. Providers may propose typed requests
but receive no scheduler/repository/executor authority.

## Authorized scope

- Create, list, inspect and cancel one-shot timers; snooze is optional.
- Use the injected UtilityClock monotonic time while running. Persist only
  bounded schedule metadata and wall-clock state needed for restart recovery;
  never persist process-local monotonic timestamps.
- Deliver elapsed timers through existing notification/chat/tray/voice policy
  and presentation arbitration. Muting, quiet hours and channel preferences
  must remain enforced.
- Prevent duplicate delivery after restart or clock changes. Define recovery
  and delivery-receipt behavior before exposing timer execution.
- Add deterministic simultaneous-timer, cancellation, shutdown, clock-change,
  restart/recovery and duplicate-delivery tests with fake clocks/repositories.

The existing utility contract reserves timers.create/list/cancel/snooze but no
inspect operation. Define inspect consistently before registry exposure; do not
invent an unvalidated provider route. The Phase 13 plan reserves migration 0015
for 13C/13D while listing its addition under 13D. Reconcile the minimal durable
timer schema with that shared reservation before creating a migration; never
add a competing schema/version or silently omit restart recovery.

## Initial work sequence

1. Specify timer identity, bounded duration/label, lifecycle, idempotency,
   cancellation race, restart/missed-expiry policy and durable receipt rules.
2. Implement framework-free timer contracts and fake-clock tests.
3. Add the single schedule service and minimal repository/migration integration
   through the existing migrator and package-data validation contract.
4. Add typed action adapters, bounded deterministic parsing and local
   clarification; preserve Phase 13B ownership/privacy guarantees.
5. Wire lifecycle/delivery to existing app and presentation boundaries and run
   focused tests. Run the full single-process gate after implementation changes.

The kickoff introduced no executor or persistence. The implementation record
below supersedes that kickoff-only state. No 13D+ reminder, weather, navigation
expansion, export, recurrence or unrestricted automation is included.

## Bounded implementation record — 2026-10-08

### Behavior and decisions

The existing action registry now contains `timers.create`, `timers.list`,
`timers.inspect` and `timers.cancel`. `TIMER_INSPECT` was added to the utility
contract consistently with request-bound schedule reads. Snooze remains a
non-executable future contract. Deterministic typed and local-voice commands
share the existing parser/envelope, action bridge, ownership guard and action
worker. Providers cannot call timers through their catalog; forged non-chat
timer requests are denied by the existing permission policy. Explicit local
requests use the existing request-bound utility authorization model and need
no filesystem grant or additional confirmation. This grants no other authority.
Missing duration or timer ID uses the existing 13B clarification service, expiry,
supersession and single-use resolution. Generic unbound CLARIFY is unchanged.

Durations are whole seconds from 1 through 604800 (seven days), with at most 100
active timers. Labels are optional, at most 64 letters/digits/spaces/hyphens/
underscores. Exact seconds/minutes/hours are supported; fractional, uncertain,
compound or oversized timer-shaped requests are rejected locally. IDs are
opaque `timer-` plus 32 lowercase hex characters. Inspect/cancel require that
exact ID; labels never select arbitrary timers. List returns active IDs and
remaining whole seconds. Labels are stored only in schedule metadata and are
omitted from action summaries, notifications and audit targets.

`TimerScheduleService` is the single schedule owner with an injected
`UtilityClock` and lock. Live deadlines use monotonic time; wall-clock changes
cannot expire or extend a live timer. Request ID plus complete normalized
fingerprint is durably bound: identical replay returns the existing timer and
does not renew its deadline, while changed content fails closed. Cancellation
and expiry race through transactional pending-to-terminal transitions. Once an
expiry receipt wins, cancellation cannot retract an already-issued notice.

Migration `0015_one_shot_timers.sql` reconciles the shared 13C/13D reservation:
only timer metadata and receipt linkage are introduced now, with no reminder
implementation. It extends the existing notification inbox's service constraint
to include timers, preserving existing rows, indexes and issued-ID high-water
state. Existing migrator transactions provide rollback. Both existing builders
already include the entire migrations directory; artifact validation now
requires 0015. No builder or clean-packaging operation was run.

UTC creation/deadline/completion timestamps, bounded state, request identity,
label and inbox receipt ID are persisted; process-local monotonic values are
never persisted. On restart, future timers recover remaining UTC duration
clamped to the original duration. Recently overdue timers (including exactly
3600 seconds overdue) expire once; older ones become missed with an inbox-only
record. Clock accuracy during downtime cannot be reconstructed. A backwards
wall clock at restart can delay recovery by at most the original duration.

Expiry and insertion into the existing Notification Center inbox commit in one
transaction before presentation. This deliberately gives durable inbox delivery
and **at-most-once channel presentation**, not guaranteed speech/chat delivery.
A crash after receipt commit leaves the inbox record and never retries channels
on restart. A database rollback leaves the timer pending for a subsequent tick.
If one claim fails after other claims committed in a batch, those committed
records remain in the inbox without channel retry. Terminal rows retain replay
receipts; automatic pruning is not implemented.

The existing notification policy, global chat/visual/voice preferences, proactive
delivery controller and opt-in speech controller govern presentation. Quiet
hours, disabled behavior, away policy and active voice/actions/clarifications
suppress channels while retaining the inbox. Suppressed notices are not queued
for a later burst. Voice uses the existing fixed Japanese timer line, mute and
speech arbitration; it does not speak private labels. Voice requires successful
chat/tray delivery through that existing route; with both visual channels off,
the result is inbox-only. A 1000 ms Qt poll means notices can appear after the
deadline by the poll interval or OS/UI scheduling delay. Shutdown stops the poll
and closes the schedule owner while retaining pending recovery metadata.

### Exact change manifest

New files:

- `project_akiha/core/utilities/timers.py`
- `project_akiha/database/migrations/0015_one_shot_timers.sql`
- `project_akiha/database/sqlite_timer_repository.py`
- `project_akiha/services/timer_schedule.py`
- `project_akiha/services/timer_actions.py`
- `project_akiha/app/timer_delivery_controller.py`
- `tests/unit/services/test_phase13c_timers.py`
- `tests/unit/app/test_phase13c_timers.py`

Modified implementation and validation support:

- `project_akiha/app/main.py`
- `project_akiha/app/proactive_delivery_controller.py`
- `project_akiha/core/actions/permissions.py`
- `project_akiha/core/actions/registry.py`
- `project_akiha/core/actions/validation.py`
- `project_akiha/core/notifications/models.py`
- `project_akiha/core/utilities/contracts.py`
- `project_akiha/database/sqlite_notification_repository.py`
- `project_akiha/services/assistant_action_bridge.py`
- `project_akiha/services/command_envelope.py`
- `project_akiha/services/package_artifact.py`
- `project_akiha/services/speech_identity.py`
- `project_akiha/ui/action_clarification_panel.py`
- `scripts/smoke_source_app.ps1`
- `tests/unit/core/actions/test_models_registry.py`
- `tests/unit/core/utilities/test_contracts.py`
- `tests/unit/database/test_migrator.py`
- `tests/unit/services/test_action_clarification.py`
- `tests/unit/services/test_package_artifact.py`
- `docs/phases/phase-13-assistant-utilities/PHASE13C.md`
- `docs/phases/phase-13-assistant-utilities/README.md`

Existing exact-registry and migration-version tests were updated for the new
timer actions/schema. The old assertion that no timer is registered now checks
the still-deferred reminder contract. Historical migration fixtures explicitly
exclude 0015 when testing earlier versions. None of these tests was disabled or
skipped. No Phase 13B implementation/test or stabilization change was removed.

### Added test coverage

`test_phase13c_timers.py` in services adds 32 enabled tests: exact monotonic
expiry, forward/backward live wall jumps, simultaneous expiry, both cancellation
orders and a barrier race, concurrent repository claims, request replay without
renewal, changed fingerprints, the 100-active cap, duration/label boundaries,
shutdown/recovery, crash-after-receipt recovery, exact grace boundary, missed
recovery, backward restart clamping, transactional receipt rollback/retry,
sanitized database/presentation failure logs, real proactive delivery and speech
preference routes, quiet/busy/channel suppression, parser/negation/compound
handling, provider denial/catalog exclusion, central missing-duration lease
identity/replay, and migration failure/retry preserving existing inbox rows and
issued-ID high water.

The app module adds six enabled composed tests through actual main wiring:
typed/local-voice convergence, real action audits/inbox/cancellation, stale and
expired clarification, invalid/provider denial, label privacy through actual
provider/export/SQLite/memory/summary/event/log surfaces, and main shutdown
preserving durable recovery. They reuse existing graph teardown, including
worker joins and GUI-thread deferred deletion. They do not inherit/duplicate
the earlier test cases. Their execution remains blocked here, not passed.

The artifact module adds a missing-0015 rejection test. Discovery is now 1917
unique test IDs (1878 prior IDs plus 38 timer tests and one artifact regression).
The historical 1878-test pass is not current implementation validation.

### Validation record

All test commands use `.venv313\Scripts\python.exe -B`. Temporary test databases
use `TEMP`/`TMP` set to the existing workspace-local
`dist\spotify-history-validation`; application smoke uses its own isolated
LOCALAPPDATA. No IPC protection, GC behavior, loop implementation, skips or
crash dialogs were changed to make a gate pass.

- Focused selection: **139 tests, OK, 3.405 s, exit 0** (`dist/phase13c-focused.log`).
  Exact selection:

```powershell
.venv313\Scripts\python.exe -B -m unittest tests.unit.services.test_phase13c_timers tests.unit.core.actions.test_models_registry tests.unit.core.actions.test_validation tests.unit.core.actions.test_permissions tests.unit.database.test_migrator tests.unit.services.test_package_artifact tests.unit.services.test_command_envelope tests.unit.services.test_assistant_action_bridge.AssistantActionRequestParserTest tests.unit.app.test_proactive_delivery_controller tests.unit.services.test_speech_identity -v
```

- Security/database/shutdown/clock/contracts: **63 tests, OK, 0.182 s, exit 0**
  (`dist/phase13c-security-db-shutdown.log`):

```powershell
.venv313\Scripts\python.exe -B -m unittest tests.unit.database.test_sqlite_notification_repository tests.unit.services.test_action_clarification tests.unit.app.test_shutdown tests.unit.core.utilities.test_clock tests.unit.core.utilities.test_contracts -v
```

- Available boundary selection: **27 tests, OK (one existing skip), 0.143 s,
  exit 0** (`dist/phase13c-boundaries-safe.log`):

```powershell
.venv313\Scripts\python.exe -B -m unittest tests.unit.services.test_phase13b_corrections.CorrectionOwnershipTest.test_atomic_publication_requires_exact_request_identity tests.unit.services.test_phase13b_corrections.CorrectionOwnershipTest.test_barrier_new_action_wins_between_owner_check_and_publication tests.unit.core.actions.test_path_policy tests.unit.core.actions.test_passive_files tests.unit.core.actions.test_tool_schemas tests.unit.core.behavior.test_notification_policy tests.unit.services.test_smoke_log -v
```

The skip is `ProtectedPathPolicyTest.test_rejects_existing_link_or_reparse_component_when_supported`:
Windows denied symlink creation with WinError 1314. No new timer test skips exist.
The broader core/action-boundary attempts blocked in pre-existing async routes;
the available selection is supporting evidence, not a full gate substitute.

- Composed timer command `-m unittest tests.unit.app.test_phase13c_timers -v`
  blocked before timer setup. A ten-second faulthandler diagnostic shows actual
  main startup at `QMessageBox.critical` after `SingleInstanceCoordinator.start`
  fails in this restricted session. Interrupted exit 1; **no final totals**.
- Required `-m unittest discover -s tests -t . -v` blocked at
  `ChatControllerTest.test_abandoned_stream_never_persists_or_processes_partial_assistant`.
  Diagnostic stack: `socket.accept` -> `_fallback_socketpair` -> Windows
  `ProactorEventLoop._make_self_pipe` -> `asyncio.run`, before timer tests.
  Interrupted exit 1; **no final totals and no complete-suite pass claimed**.
  Logs: `dist/phase13c-full.log`, `dist/phase13c-full-ipc-diagnostic.log`.
- Historical Qt pair was attempted in its exact order. First repetition:
  **2 tests, failures=2, 4.047 s**, hosted readiness and worker-join failures,
  followed by process exit **-1073740791**. Ten successful repetitions are not
  claimed. This worker uses the same environment-blocked asyncio startup;
  owner unrestricted verification must establish current lifecycle behavior.
  No timer code participates in this pair. Log `dist/phase13c-qt-pair-1.log`.
- Source/database/log smoke:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/smoke_source_app.ps1 -SmokeRoot "$PWD\dist\phase13c-source-smoke" -PythonExe "$PWD\.venv313\Scripts\python.exe" -StartupSeconds 2 -ShutdownSeconds 1
```

  **Exit 1**: isolated `Akiha` data directory not created; startup blocked before
  database/log initialization. No source smoke or graceful-shutdown pass claimed.
  Independent real SQLite timer/migration/inbox tests and smoke-log validator
  tests passed above. They do not substitute for application smoke.

- Final timer-only rerun: **32 tests, OK, 2.041 s, exit 0**:
  `-m unittest tests.unit.services.test_phase13c_timers -v`
  (`dist/phase13c-timers.log`).
- Ruff: `-m ruff check project_akiha tests`, **exit 0**, all checks passed
  (`dist/phase13c-ruff.log`).
- Black check used the single-process Black API, with line length 88 and
  Python 3.12 target, on all 559 project/test Python files: **all unchanged,
  exit 0**. The ordinary multiprocess CLI is subject to the same IPC restriction.
- In-memory `compile(source, filename, 'exec')` on those **559 files passed**;
  AST core import boundaries passed. Discovery found **1917 unique IDs**, no
  loader errors. Command: `python -B dist/spotify-history-static-check.py`,
  **exit 0**, `dist/phase13c-static.log`. This existing ignored local harness
  also checks earlier history tests; it does not execute the full suite.
- Separate new-test inventory check: **38 unique enabled timer test IDs**, no
  duplicate method names or skip/GC-disable directives. Output:
  `dist/phase13c-new-test-inventory.json`. Static checks confirm both existing
  builders include the migrations directory. No package was built.
- `git -c safe.directory='C:/Users/MY PC/Desktop/Project Akiha' diff --check`:
  **exit 0**. Exact working-tree manifest: **29 files**, all listed above.
- A final required discovery attempt after the last implementation/test change
  again blocked at the same earlier ChatController test and was interrupted
  with **exit 1, no final totals** (`dist/phase13c-full-final.log`). No later
  implementation/test changes were made after that attempt.

### Unrestricted Windows verification handoff

Run from this checkout in normal PowerShell. These commands preserve IPC and
single-instance protections and capture each exit code. Return the entire new
verification folder. Do not run a clean package build.

```powershell
Set-Location 'C:\Users\MY PC\Desktop\Project Akiha'
$timerVerifyDir = Join-Path $PWD ('dist\phase13c-verification-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Path $timerVerifyDir | Out-Null
$timerPython = Join-Path $PWD '.venv313\Scripts\python.exe'
$env:TEMP = Join-Path $timerVerifyDir 'temp'
$env:TMP = $env:TEMP
New-Item -ItemType Directory -Path $env:TEMP | Out-Null

& $timerPython -B -m unittest tests.unit.services.test_phase13c_timers tests.unit.app.test_phase13c_timers -v *> (Join-Path $timerVerifyDir 'timers.log')
$LASTEXITCODE | Set-Content (Join-Path $timerVerifyDir 'timers.exitcode.txt')

& $timerPython -B -m unittest discover -s tests -t . -v *> (Join-Path $timerVerifyDir 'full.log')
$LASTEXITCODE | Set-Content (Join-Path $timerVerifyDir 'full.exitcode.txt')

for ($timerRun = 1; $timerRun -le 10; $timerRun++) {
    & $timerPython -B -m unittest tests.unit.ui.test_behavior_history_window.BehaviorHistoryWindowTest.test_clear_matching_emits_selected_filters_after_confirmation tests.unit.ui.test_hosted_live_session_worker.HostedLiveSessionThreadTest.test_tool_task_failure_stops_visibly_instead_of_stranding_turn -v *> (Join-Path $timerVerifyDir "qt-$timerRun.log")
    $LASTEXITCODE | Set-Content (Join-Path $timerVerifyDir "qt-$timerRun.exitcode.txt")
}

& $timerPython -B -m ruff check project_akiha tests *> (Join-Path $timerVerifyDir 'ruff.log')
$LASTEXITCODE | Set-Content (Join-Path $timerVerifyDir 'ruff.exitcode.txt')
& $timerPython -B -m black --check project_akiha tests *> (Join-Path $timerVerifyDir 'black.log')
$LASTEXITCODE | Set-Content (Join-Path $timerVerifyDir 'black.exitcode.txt')

powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/smoke_source_app.ps1 -SmokeRoot (Join-Path $timerVerifyDir 'smoke-data') -PythonExe $timerPython *> (Join-Path $timerVerifyDir 'smoke.log')
$LASTEXITCODE | Set-Content (Join-Path $timerVerifyDir 'smoke.exitcode.txt')
Write-Output $timerVerifyDir
```

Expected timer selection: 38 tests; complete discovery: 1917 for this exact
working tree. The source smoke's graceful/forced-stop fields must be reviewed
separately; its exit code alone does not prove graceful pending-clarification
shutdown. Close the isolated source-smoke instance if its startup privacy dialog
requires interaction; never bypass single-instance safeguards.

### Manual commands and remaining review

Type, or use the existing local-voice transcript route:

- `Set a timer for 10 seconds`
- `Akiha, please set a timer for 2 minutes named tea`
- `Set a timer` (answer the local field with whole seconds, e.g. `10`)
- `List timers` or `/timers`
- `Inspect timer timer-<copy the exact ID from List timers>`
- `Cancel timer timer-<copy the exact ID>`
- `/timer 30 seconds`

Use actual IDs, not angle brackets. Confirm notification preferences, quiet
hours, muted/active voice, cancellation, exact expiry and restart recovery in
the normal Windows source app. Verify providers/chat/export/memories/audit logs
do not receive a synthetic private label, including during clarification.
No live microphone/provider/TTS verification has been performed in this pass.
Independent review and owner acceptance remain required. No commit, push,
completion, clean packaging or Phase 13D+ implementation occurred.

## Carried follow-up obligations

- FOLLOWUP-13B-SHUTDOWN: graceful shutdown with a pending clarification remains
  unproved and explicitly deferred by the owner.
- FOLLOWUP-13B-PACKAGE: packaged smoke remains explicitly deferred.
- FOLLOWUP-CLEANUP-GUARD: fix and verify the destructive WorkDir cleanup guard
  before any clean packaging. Phase activation does not waive this prerequisite.

These items remain tracked in the [13B closing review](../../audits/PHASE13B_BOUNDED_REVIEW_2026-10-08.md).
Phase 13C activation is not package/release acceptance.

## Owner functional acceptance — 2026-10-09

The owner reported that the timer commands work well during manual testing and
explicitly requested acceptance: “Looks good, it works so far the task timer
commands is working well proceed to accept it since I manually tested it”.
Owner acceptance of the implemented timer behavior is recorded on that basis.
The owner did not supply a command-by-command test matrix or new automated
results; this record does not infer microphone, restart, race, privacy or failure
case verification beyond the reported manual checks.

The automated results and blocked gates above remain unchanged. Independent
review, the six composed tests, required single-process complete discovery,
historical Qt lifecycle verification and source smoke still need unrestricted
Windows evidence. Manual acceptance is not recorded as an automated gate pass
or an explicit waiver of those requirements. Phase 13C remains active until its
remaining verification and review are resolved; Phase 13D is not activated.
The deferred shutdown/package checks and cleanup-guard prerequisite remain
in force. This update changes documentation only.

## Automated gates and bounded review follow-up — 2026-10-09

See the [bounded review record](../../audits/PHASE13C_REVIEW_2026-10-09.md) for
the exact reviewed locations, independent probes, fresh results and limitations.
Owner timer-behavior acceptance above is preserved. No new implementation defect
was reproduced. One composed test incorrectly dispatched a worker after central
readiness had already rejected a fractional duration; the actual production
callback probe reproduced this, and the test now asserts early rejection,
zero worker creation, no provider prompts and no rows. Independent code
and repository probes passed, but composed privacy/lifecycle verification and
required automated gates remain blocked by this session's local IPC restrictions.
Phase 13C remains active, not complete. Phase 13D has not started.

Fresh runs: focused 139 tests OK; security/database/shutdown 63 OK; available
boundaries 27 OK with one existing Windows symlink-privilege skip. Ruff, Black
API, compilation of 559 files and static boundaries pass. Inventory remains
1917 unique IDs, including 38 enabled timer tests. Composed/full discovery were
interrupted with exit 1 and no final totals; source smoke exited 1 before data
initialization. The default Windows asyncio socket-pair and QLocalServer access
failures were independently reproduced without timer code.

The new verification-only script captures all required normal Windows gates,
full discovery in one process, ten historical Qt-pair repetitions, inventory and
content hashes. Syntax and real inventory-only execution passed. This script
does not clean/package, change app configuration, bypass IPC or disable tests.
Its full mode still needs unrestricted execution; it returns nonzero if a gate
returns nonzero. Run:

```powershell
Set-Location 'C:\Users\MY PC\Desktop\Project Akiha'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify_phase13c.ps1
```

Return the entire printed verification folder, including `gate-results.json`,
individual logs/exit codes, `inventory.json`, `file-hashes.json`, `head.txt` and
`status.txt`. Completion requires reconciling this evidence against the reviewed
tree and finishing the blocked composed checks. Existing shutdown/package
deferrals and the cleanup-guard prerequisite are unchanged.

## Normal Windows evidence and gate corrections — 2026-10-09

Reviewed `dist/phase13c-verification-20261009-025651-5d46ef` completely for gate
results and failure traces. All captured source hashes matched the pre-correction
tree. Inventory contains 1924 unique IDs; every ID occurs in the wrapped full
output. Full discovery completed in one process: 1924 tests, 53.152 seconds,
two failures, no skips, exit 1. Timer selection: 38 tests, 4.073 seconds,
one failure, exit 1. These are failed gates, not IPC failures.

The real composed privacy test reproduced a timer label entering the visible
chat transcript through `submit_chat_message`'s unconditional user-message
append. Other checked persistence/provider/output surfaces excluded the label.
The composer now omits the user-message echo for recognized typed timer actions;
the original request and label still reach the existing action validation and
schedule owner. Other action/chat display routing is preserved. The composed
privacy test now asserts exclusion immediately after submission, and the
typed/local-voice convergence test also asserts label exclusion from the UI.

The full suite's second failure was
`GptSoVitsEngineManagerTest.test_missing_runtime_is_reported`. A targeted rerun
reproduced it: TEMP inside the checkout allowed the production four-ancestor
runtime search to discover the actually installed runtime, yielding `starting`.
The missing-runtime fixture now places its empty root five levels inside its
temporary directory and asserts all discovery roots stay within that fixture.
Runtime discovery, process behavior and assertions remain intact. This is a
test isolation defect, not a timer or live-synthesis failure.

Post-correction commands and results:

- `.venv313/Scripts/python.exe -B -m unittest tests.unit.services.test_gpt_sovits_engine_manager tests.unit.services.test_phase13c_timers -q`:
  43 tests, 1.938 seconds, OK, exit 0 (TEMP/TMP set to workspace fixture directory).
- `.venv313/Scripts/python.exe -B dist/phase13c-composer-probe.py`: actual
  production composer callback and real ChatWindow; private-label exclusion,
  intact request label and other-action display all pass, exit 0. This bounded
  probe is supplemental, not a replacement for composed/full discovery.
- `.venv313/Scripts/python.exe -B -m ruff check project_akiha tests`: exit 0.
- `.venv313/Scripts/python.exe -B dist/spotify-history-static-check.py`:
  560 files compile, Black API unchanged, core boundaries pass, 1924 unique IDs,
  exit 0. Black CLI remains covered by the owner's prior normal run.
- `git -c safe.directory='C:/Users/MY PC/Desktop/Project Akiha' diff --check`:
  exit 0.

Owner-run unchanged gates passed: focused 139, security/database/shutdown 63,
boundaries 39, cleanup guard 7 (including real junction assertions), ten Qt
pairs of two tests each, Ruff, Black CLI, compilation/static and diff check.
The cleanup guard prerequisite is now independently verified at the captured
hashes; no packaging occurred. Source/database/log smoke exited 0 but recorded
`ForcedStop=True`; graceful shutdown remains unproved.

Changed by this gate correction: `project_akiha/app/main.py`,
`tests/unit/app/test_phase13c_timers.py`,
`tests/unit/services/test_gpt_sovits_engine_manager.py` and these review/work
records. The current inventory remains 1924. Corrected composed timer and full
single-process gates require normal Windows rerun because this session's
previously reproduced IPC restriction remains. Run the same verification
script above and return its new folder. Phase 13C remains active with owner
functional acceptance preserved; the already authorized 13D–13I work remains
queued behind this required dependency. No completion, new acceptance, commit,
push or package is recorded.

## Final correction verification and completion — 2026-10-09

Reviewed `dist/phase13c-verification-20261009-030430-a61707`. All captured hashes
match the corrected tree; inventory is 1924 unique IDs and every ID occurs in
the full output. The required one-process discovery ran 1924 tests in 48.545
seconds, OK, no skips, exit 0. Timer selection ran 38 in 4.739 seconds, OK,
exit 0. Focused 139, security/database/shutdown 63, boundaries 39, cleanup guard
7 (including the real junction fixture), and ten historical pairs of 2 tests
each all passed. Ruff, Black CLI, compilation/static, isolated source/database/
log smoke and diff check all exited 0. The exact command was
`powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify_phase13c.ps1`.

Both previously reproduced failures are now covered by the successful composed
and full gates. Bounded review found no remaining timer acceptance blocker.
The owner's already recorded functional acceptance is preserved. Phase 13C is
complete and Phase 13D is active under the existing continuous authorization.
Smoke still records ForcedStop=True, so graceful shutdown is not claimed.
The cleanup guard prerequisite is verified; final source/package/shutdown gates
and the owner's consolidated checklist remain outstanding. No commit or push.

### Consolidated follow-through — 2026-10-09

The authorized dependency-ordered 13D–13H implementation and 13I source gates
are recorded in [CONSOLIDATED_VERIFICATION.md](CONSOLIDATED_VERIFICATION.md).
Current discovery passes 1990 tests in one process, zero skips, exit 0; the
historical 1924 total above remains the reviewed 13C-only milestone. Ten Qt
pairs and all seven cleanup tests pass. A fresh clean candidate was built only
after those gates and the cleanup prerequisite passed. Pending-clarification
Quit is now proved in source and package in fresh default profiles; real
configured hosted/microphone shutdown remains an explicit owner checklist
item. Owner timer acceptance is preserved; final consolidated Phase 13
acceptance is pending. No commit or push was made.
