# Phase 13C bounded review — 2026-10-09

Historical verdict below is superseded by the reviewed passing rerun and
completion addendum at the end of this record.

Verdict: **not ready for phase completion; required gates remain blocked**.
No new implementation acceptance defect was reproduced in the available
independent probes. This is not a full composed-application privacy or lifecycle
pass. Owner functional acceptance of timer behavior remains recorded and is
not revoked or expanded by this review.

## Reviewed implementation and scope

Reviewed PHASE13C.md completely, the implemented timer commit `c584749`, its
change manifest, the Phase 13 plan and 13D checklist, and the actual timer
contracts, parser, executor, registry, validation, permission policy, repository,
migration 0015, single schedule owner, delivery policy, main wiring, notification
model/reader, provider catalog and composed tests. The current implementation
adds no reminder, recurrence, weather, navigation expansion or export feature.
No implementation changes were made during this review. One composed-test
routing assumption was reproduced and corrected as described below.

The action registry validates duration/label/ID shapes. The explicit local
request-bound timer permission branch does not grant filesystem or Spotify
authority. Timers remain absent from the provider catalog. Clarification uses
the existing controller and leases; ownership guards and stale result rejection
remain in the action worker/composition. Inspect/cancel use opaque exact IDs.

Live deadlines use monotonic time. Restart recovery uses UTC metadata with a
documented one-hour overdue grace and original-duration clamp. Cancellation
and expiry serialize through pending-state database transitions. Receipt and
inbox insertion are atomic; already-claimed timers never replay after restart.
Presentation is intentionally at most once. Suppressed/failed channels retain
the durable inbox rather than retrying or speaking later. Partial batch failure
can leave committed inbox receipts without channel presentation; this is an
explicit implementation limitation, not silently claimed guaranteed delivery.

Quiet/away/behavior policy, global channel preferences and existing proactive
speech arbitration remain on the delivery route. Labels are excluded from
executor summaries, notification text, normalized audit targets and generic
error logs. The migration preserves existing inbox rows/indexes and issued-ID
high water. The existing builders collect the migration directory; the artifact
validator requires 0015. No clean packaging occurred.

## Independent probes

An independent inline Python probe used a fresh temporary SQLite database,
actual migrations 1–14, a cleared inbox after issuing ID 300, the production
timer repository/schedule owner/notification reader, a separately defined clock,
actual local command parser, validator, permission policy and provider catalog.
It did not import the new timer regression tests.

The probe passed all assertions: migration after cleared history retains issued
ID high water; a two-day backwards live wall jump does not alter monotonic
expiry; exact expiry produces one receipt; identical request replay does not
renew; changed fingerprint rejects; cancellation after receipt loses; restart
does not redeliver; cancelling before expiry prevents a second inbox receipt;
the synthetic label is absent from the real inbox; a provider-source timer
request is denied and the provider catalog rejects timer resolution. Exit 0;
log `dist/phase13c-review-probes.log`. No real account, microphone, TTS or
private user dialogue was used.

These probes establish repository/action-boundary properties, not the unavailable
full application privacy paths. The six composed timer tests use actual main
wiring, real SQLite actions/audits, composer, voice transcript routing, provider
message construction, export, memories/summaries, events/logs and notifications.
Their external provider and worker transport are controlled doubles. They reuse
GUI-thread teardown and worker joins and do not inherit older test cases. Their
runtime assertions still need execution in unrestricted Windows.

### Reproduced test defect and bounded correction

The composed invalid/provider test sent `Set a timer for 1.5 minutes` and then
called `dispatch()` on a worker that production never creates. The actual parser
produces an invalid duration, central readiness rejects it, and main's
`start_action_thread` returns after a local notice. A fresh probe executed the
actual parser/controller and the unchanged production callback extracted from
main's AST, asserting zero worker creation and a local rejection notice. Exit 0;
`dist/phase13c-review-invalid-probe.log`. This extraction is a bounded callback
probe, not full application composition or an IPC bypass.

`tests/unit/app/test_phase13c_timers.py` now asserts unchanged worker count,
no provider prompts and no timer rows immediately after that rejected command.
The forged-provider denial assertions remain intact. No application validation
was weakened, test skipped or new test duplicated. Total inventory remains 1917
and the timer selection remains 38. The corrected composed test still requires
unrestricted execution; this probe is not claimed as its passing result.

After the correction, Ruff exited 0, the changed test compiled and passed its
Black API check, and the real handoff inventory/static mode exited 0 with
1917 unique IDs, 38 timer tests and 559 compiled Python files
(`dist/phase13c-verification-20261009-024253-980246`). Required full discovery
was retried because a test changed; it again blocked after the existing
autonomous-controller tests and was interrupted with exit 1 and no final totals
(`dist/phase13c-review-full-after-correction.log`). `git diff --check` passed.

## Fresh command results

Commands use `.venv313\Scripts\python.exe -B`; test TEMP/TMP point to the existing
workspace `dist\spotify-history-validation`. Exact named selections are in
PHASE13C.md and the checked-in verification script.

| Check | Fresh result | Output |
|---|---|---|
| Focused selection | 139 tests, OK, 3.082 s, exit 0 | `dist/phase13c-review-focused.log` |
| Security/SQLite/shutdown/clock/contracts | 63 tests, OK, 0.195 s, exit 0 | `dist/phase13c-review-security.log` |
| Available action/boundary selection | 27 tests, OK with one existing skip, 0.174 s, exit 0 | `dist/phase13c-review-boundaries.log` |
| Ruff `-m ruff check project_akiha tests` | All checks passed, exit 0 | tool output |
| Existing static harness `dist/spotify-history-static-check.py` | 559 files compile; Black API unchanged; AST core boundaries pass; 1917 unique discovered tests; exit 0 | `dist/phase13c-review-static.log` |
| Independent probes | All assertions pass, exit 0 | `dist/phase13c-review-probes.log` |
| Composed `-m unittest tests.unit.app.test_phase13c_timers -v` | Blocked before timer setup; interrupted exit 1, no final totals | `dist/phase13c-review-composed.log` |
| Required `-m unittest discover -s tests -t . -v` | Blocked after existing autonomous-controller tests; interrupted exit 1, no final totals | `dist/phase13c-review-full.log` |
| Source/database/log smoke | Isolated Akiha data directory not created; exit 1 | `dist/phase13c-review-smoke.log` |
| Handoff script syntax and `-InventoryOnly` | Syntax pass; actual inventory/static capture exit 0 | `dist/phase13c-verification-20261009-023915-c369f8` |

The existing symlink/reparse test skips with WinError 1314 (missing Windows
symlink privilege); no new timer test was skipped. Inventory is 1917 unique test
IDs, including 38 enabled timer tests. Neither 1917 discovered tests nor the
prior 1878-test success is a current complete-suite pass.

Independent QLocalServer(UserAccessOption) probe returned false with
`QLocalServerPrivate::addListener: Access is denied.` Default Windows
`asyncio.run(asyncio.sleep(0))` also blocked; a three-second faulthandler snapshot
shows `socket.accept` / `_fallback_socketpair` / Proactor `_make_self_pipe`,
before any Akiha timer code. Interrupted exit 1; log
`dist/phase13c-review-ipc.log`. No loop/IPC protection was replaced or bypassed.
The historical Qt pair already failed under this restriction during timer
implementation; no ten-pass repetition is asserted or unnecessary further Qt
abort provoked in this review. Its ten current unrestricted repetitions remain
in the handoff. Graceful pending-clarification shutdown remains unproved.

## Unrestricted evidence still required

Run `scripts/verify_phase13c.ps1` from normal Windows PowerShell. It captures
each log/exit code, the current discovered inventory, HEAD/status, content hashes,
all 38 timer tests, focused/security/boundary selections, full discovery in one
process, ten historical Qt-pair repetitions, Ruff, Black CLI, compilation/static
boundaries, isolated source/database/log smoke and `git diff --check`.
It does not split the required complete suite, disable GC/tests, override IPC,
change app configuration, suppress crash dialogs, clean WorkDir or package.
Its overall exit is nonzero if any captured gate exits nonzero. Inventory-only
mode is a harness check and is not a test-suite pass.

Return the printed folder for reconciliation: every discovered ID must occur in
the full run, final unittest totals and exit 0 are required, all timer tests must
be enabled/executed, skips must be explained, hashes must match the reviewed
tree, and source smoke's forced-stop result must be classified independently
of its exit code. Correct only defects reproduced by that evidence.

Phase completion is not recorded. Owner acceptance, FOLLOWUP-13B-SHUTDOWN,
FOLLOWUP-13B-PACKAGE and FOLLOWUP-CLEANUP-GUARD remain intact. No clean packaging
until the destructive WorkDir guard is fixed and verified. Phase 13D is not
started. Its documented scope is one-shot reminders with explicit local date,
time and timezone; list/cancel/snooze on the existing schedule owner; bounded
missed-reminder recovery; approved minimal persistence through the existing
migrator. Recurring reminders remain deferred.

## Unrestricted evidence reviewed and corrections

Reviewed folder `dist/phase13c-verification-20261009-025651-5d46ef`: all captured
hashes match the pre-correction tree; all 1924 inventory IDs occur in full output.
Required full gate: 1924 tests, 53.152 seconds, two failures, no skips, exit 1.
Timer gate: 38 tests, 4.073 seconds, one failure, exit 1. Actual privacy failure:
timer command label echoed into UI canonical transcript; no evidence of leakage
in the other connected surfaces. The composer now suppresses typed timer action
echo while preserving the original validated request and other action display.
Connected assertions strengthened for immediate exclusion and local voice.

Second full failure reproduced independently with workspace TEMP: the empty
GPT-SoVITS fixture searched checkout ancestors and found the installed runtime.
The fixture now contains all four ancestor search locations in an empty nested
tree; runtime implementation is unchanged. Both defects are corrected, but
corrected full/composed gates are pending unrestricted rerun.

Available post-correction checks: 43 timer-service/manager tests OK, actual
composer + real Qt chat-widget probe OK, Ruff OK, Black API 560 unchanged,
560 compiled files, static boundaries, 1924 unique inventory and diff check OK.
Exact commands are recorded in PHASE13C.md. Owner-run focused 139,
security/database/shutdown 63, boundaries 39, guard 7 and ten Qt pairs passed.
Guard junction test passed normally, closing the guard verification prerequisite
at unchanged hashes. Source smoke exit 0 still forced termination, proving no
graceful-shutdown result. No packaging, phase completion, commit or push.

## Passing rerun and completion addendum

Reviewed owner's `phase13c-verification-20261009-030430-a61707`: all captured
implementation hashes match; 1924 unique discovered/executed IDs; 1924 tests
in one process, 48.545 seconds, OK, no skips, exit 0. All timer/focused/security/
boundary/quality/static gates, seven guard tests including the actual junction,
and ten historical Qt pairs pass. No remaining timer blocker was reproduced.
Existing owner functional acceptance was preserved, completing 13C before 13D.

The continuous 13D–13I follow-through now passes 1990 tests in one process with
no skips and a fresh consolidated candidate. Source/package pending-clarification
Quit now has normal exit-0 proof in fresh default profiles, separately from the
legacy forced-stop startup harness. See
[consolidated evidence](../phases/phase-13-assistant-utilities/CONSOLIDATED_VERIFICATION.md)
for exact scope, commands, review/probes, privacy, manifest and limitations.
Final owner consolidated acceptance, including real configured sessions,
remains pending. No commit or push was made by this task.
