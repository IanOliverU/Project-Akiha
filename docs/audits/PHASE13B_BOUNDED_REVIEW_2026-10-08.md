# Phase 13B bounded closing review — 2026-10-08

Verdict: PASS for the bounded Phase 13B closing review, with the owner's explicit
shutdown/package deferrals. The owner supplied ten passing unrestricted Qt-pair
runs after the restricted attempts below. Phase 13B acceptance and closure are
recorded on 2026-10-08; Phase 13C is authorized and active.

## Current unrestricted evidence

Owner-generated results are under
`dist/phase13b-rerun-20261008-124002/` (ignored verification artifacts).

- Connected selection: 14 tests, 2.487 seconds, OK, exit 0.
- Required single-process full discovery: 1,878 tests, 40.912 seconds, OK,
  exit 0, no skips, failures or errors.
- Captured inventory: 1,878 unique IDs, exactly matching current discovery.
  Every current ID appears in the complete-run output.
- Baseline checkpoint: `6c879b1e77e53b3a16b7dc24c382996b8712be97`.
  The rerun includes the subsequent SQLite test cleanup correction.
- The earlier isolated source smoke verified database tables and the smoke log,
  exit 0, but reported `CloseMainWindowRequested=False`, `ForcedStop=True`
  and application exit -1. It does not prove graceful shutdown.

The required full suite was not repeated during this bounded closing review.

## Review scope and findings

Reviewed central lease publication and identity/fingerprint enforcement;
local directory/media callback admission; app/root/music choice construction
and resolution; composer routing and deliberate local chat override; strict
provider aliases; Gemini suspension and stale-audio handling; Spotify history
retrieval/publication/selection/account binding; and Qt test cleanup.

The production service retains locked ownership checks and publication.
Local-search identities bind the full original request, epoch, fingerprint,
source, operation, generation, nonce, creation and deadline. Discovery admission
and ready-result enqueueing validate ownership; worker cancellation rechecks
authority. Approved-root/path/permission and confirmation checks remain downstream.

History fetches the latest 20 plays, deduplicates by track URI in newest-first
order and shows at most 10 distinct entries. Search retains its separate cap
of five. History permission is checked without expanding authorization; selection
retains account generation and existing playback authority. Picker data and
history execution result presentation use the local/private and sanitized routes.

Connected tests use application callbacks, Qt signals, real ChatController,
temporary SQLite, provider-message construction, export, actual memory and summary
persistence, notification delivery, EventBus/EventLogger and application logs.
Synthetic external transports avoid real account calls and playback. Positive
public-content persistence controls prevent empty-output privacy false positives.
The unrestricted passing selection supports these routes; it is not a claim of
live microphone, provider, Spotify account or graceful shutdown verification.

An additional independent stdin probe exercised the actual production service,
controller and alias resolver: 72 assertions passed, exit 0. It covered directory
and media zero/multiple/limited-single/unique outcomes after supersession,
revocation, cancellation, exact expiry and changed fingerprints; valid owned
outcomes and replay; stale confirmation; typed/local-final-transcript embedded,
encoded and oversized private replies; ordinary non-path conversation; and
punctuation/traversal/URI/encoded aliases. No execution or persistence occurred.
No new implementation blocker was found within this bounded scope.

## Historical Qt pair

The exact pair was attempted ten times, in this order, in one Python process
per attempt:

```powershell
.venv313\Scripts\python.exe -B -m unittest tests.unit.ui.test_behavior_history_window.BehaviorHistoryWindowTest.test_clear_matching_emits_selected_filters_after_confirmation tests.unit.ui.test_hosted_live_session_worker.HostedLiveSessionThreadTest.test_tool_task_failure_stops_visibly_instead_of_stranding_turn -v
```

Every attempt reported `Ran 2 tests` and two failure events in the
hosted test (readiness and cleanup join); the behavior-history test passed.
Attempt 1 exited 1; attempts 2–10 exited -1073740791 after the failed cleanup.
Their logs are under `dist/phase13b-qt-review-20261008/`. The previously captured
trace identifies the restricted Windows asyncio socket-pair setup as the worker
startup blocker. The abnormal exits after failure are not passing Qt evidence;
this review does not classify them as a newly introduced application defect.

Source cleanup closes/deletes widgets on the GUI thread, processes deferred
deletion, resets QMessageBox mock history, and requires hosted workers to join
before deferred disposal. No GC disabling, crash-dialog suppression, IPC bypass,
test weakening or subprocess splitting of the full-suite gate was introduced.
The owner then ran the exact pair ten times in the unrestricted environment.
`dist/phase13b-qt-owner-20261008-133352/` contains each output and exit file:
every run reports two tests, OK, exit 0, without skips or errors. Elapsed seconds
for attempts 1–10: 0.071, 0.070, 0.072, 0.071, 0.073, 0.060, 0.071, 0.070,
0.071, 0.069. This supplies the passing repetition evidence without weakening
tests or repeating the complete suite. The restricted failures remain historical
environment evidence and do not invalidate these unrestricted results.

## Owner-authorized deferrals and transition condition

The owner explicitly authorized deferring these items on 2026-10-08:

- FOLLOWUP-13B-SHUTDOWN: graceful application shutdown with a pending
  clarification. Exercise an actual pending lease and establish worker joining,
  database closure and normal process exit. Current status: unproved.
- FOLLOWUP-13B-PACKAGE: packaged smoke. Prerequisite FOLLOWUP-CLEANUP-GUARD:
  fix and verify the destructive WorkDir cleanup guard before any clean packaging.
  No clean packaging is permitted until that prerequisite is satisfied.

The owner's conditions to accept 13B and activate 13C are now satisfied by the
closing review and unrestricted ten-repeat evidence. Acceptance and activation
are recorded with the explicit deferrals above. The documented 13C plan was read:
one-shot timer create/list/inspect/cancel (optional snooze), monotonic runtime
timing, minimal wall-clock recovery state, existing notification/presentation
routes, duplicate-delivery protection and deterministic lifecycle/recovery tests.
The 13C kickoff records the bounded timer scope and reused contracts; no timer
executor, migration, reminder, weather or export functionality was added during
the closing review.

The SQLite correction uses `contextlib.closing` around the test inspection
connection. Privacy assertions are unchanged. Ruff, Black and diff checks passed
for that correction before the unrestricted rerun. No commit or push is claimed
by this review record.
