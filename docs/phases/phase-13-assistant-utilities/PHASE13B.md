# Phase 13B implementation and verification

Status: complete; owner accepted Phase 13B on 2026-10-08 with the explicit
shutdown/package deferrals below. Phase 13C is authorized and active.

## Final owner acceptance — 2026-10-08

The owner reported successful manual functional checks and authorized acceptance
after a bounded closing review and ten successful historical Qt-pair repetitions.
Those conditions are now satisfied:

- Unrestricted connected selection: 14 tests, OK, exit 0.
- Unrestricted single-process complete discovery: 1,878 tests, OK, exit 0,
  no skips, failures or errors. The inventory exactly matches current discovery.
- Ten unrestricted historical Qt-pair runs: two tests each, every run OK,
  exit 0, no skips or errors. Evidence:
  `dist/phase13b-qt-owner-20261008-133352/`.
- Bounded review: no new implementation blocker; 72 independent production
  service/controller probes passed. SQLite inspection cleanup now closes the
  connection explicitly without changing privacy assertions.

The owner explicitly deferred FOLLOWUP-13B-SHUTDOWN (graceful shutdown while a
clarification is pending) and FOLLOWUP-13B-PACKAGE (packaged smoke). Graceful
pending-clarification shutdown remains unproved. FOLLOWUP-CLEANUP-GUARD is a
mandatory prerequisite: fix and verify the destructive WorkDir cleanup guard
before any clean packaging. Source smoke verified database/log initialization,
but its forced stop does not satisfy the deferred graceful-shutdown check.

See [the bounded closing review](../../audits/PHASE13B_BOUNDED_REVIEW_2026-10-08.md)
and [the 13C kickoff](PHASE13C.md). The owner's acceptance with these deferrals
does not waive the cleanup prerequisite or assert package/release acceptance.
Historical pending/blocked records below describe earlier revisions and are
superseded by this closure record. Commit and push status must be checked from
Git; this record makes no claim that they have succeeded.

## Requirement-to-test checklist (recorded before implementation)

| Requirement | Planned verification |
| --- | --- |
| Ready, missing/zero-match, multiple-match requests; original operation | Core readiness tests; controller and discovery integration tests |
| 120-second absolute lifetime; partial revision; no extension | Fake-clock service tests at exact boundary and after revision |
| One foreground question; supersession; unrelated conversation | Controller routing and service lifecycle tests |
| Identity, revision, target/arguments, replay, cancellation | Wrong-request and mutation tests; concurrent consumption tests |
| Local answers only; cloud pause | Hosted worker and UI/controller tests |
| Open-any only by trusted local UI | Provider/free-text rejection and explicit UI selection tests |
| Absolute provider paths; duplicate root aliases | Gateway and local alias-map tests |
| Revocation immediately invalidates pending state | Permission-service listener integration tests |
| Separate 60-second confirmation; after grants | Dispatcher/service integration, expiry, mutation and replay tests |
| Native batches cannot partially execute | Google/Ollama batch contracts and worker/gateway tests |
| Five proposal lanes use shared handling | Chat, modular voice, JSON, Ollama, Gemini regression tests |
| No transcript, summary, memory, prompt, notification or log leakage | Recording surfaces/repositories/providers/logger privacy tests |
| Sanitized lifecycle evidence only | Closed-field evidence tests |
| Uncertain times: contracts only | Temporal reason contracts; no new registry/tool/migration tests |
| Existing boundary regressions | Full unittest, Ruff, Black, compileall and source smoke gates |

## Inputs

The readiness report is the read-only review in the implementation conversation.
No AGENTS.md, separate ACTION_SYSTEM.md, SECURITY_MODEL.md, or ADR files exist
in this checkout. The maintained Phase 8/13 plans, CODEBASE_STRUCTURE.md,
SECURITY_REVIEW.md and LOCAL_DATA_PRIVACY.md are the current references.

## Owner decisions

Clarification lasts 120 seconds and confirmation 60 seconds, measured against an
injected monotonic clock. Neither deadline extends. One foreground clarification
may exist. Partial answers revise it; unrelated conversation leaves it pending;
a new explicit action supersedes it. File/directory choices are bounded to ten
and Spotify choices to five. Cloud-origin clarification requires cloud audio to
pause and a trusted local UI answer. Open-any is a local UI choice only.
Questions/answers and private pending payloads never enter canonical chat,
provider context, summaries, memory, notifications or ordinary logs. No migration
or later utility implementation is included. Existing playback labels are not
broadened. Global idempotency is unchanged.

## Follow-up outside this phase

The Phase 8 backlog and documentation index contain historical roadmap/status
wording. Reconcile that history separately; it does not reopen completed phases.


## Implemented boundaries and behavior

The composition root shares one controller and lease owner with typed chat,
accepted modular voice input, strict JSON classifier proposals, Ollama native
tools and Gemini Live. Framework-free contracts stay in core; the service owns
locked transitions, private immutable request/choice snapshots and an in-memory
128-record sanitized evidence ring. The app controller prepares requests and
assembles local candidates; the Qt panel renders them outside the transcript.
The existing registry, permission service, action service, command envelopes,
intent arbiter, EventBus and notification pipeline retain their existing roles.

A lease identity binds opaque ID/nonce, process owner epoch, request digest,
revision, creation and deadline. The digest covers correlation ID, operation,
source and normalized primitive arguments; selected targets come from the
immutable locally held candidate snapshot. Wrong identity, changed arguments,
old revision, expiry, duplicate consumption and replay cannot resume execution.
A repeated preparation of the same foreground request does not renew its
lifetime. Valid partial answers increment revision and preserve the deadline.
Each accepted explicit action claims ownership before readiness evaluation,
including incomplete actions. Process-local request-ID/digest bindings reject
changed content even after resolution; trusted lease answers update that binding.
Late results and confirmation issuance require the captured ownership epoch.
String/catalog, bounded integer and exact boolean parameters retain their
registered types; this does not interpret uncertain timer/reminder expressions.

Missing fields and unknown provider root aliases ask locally. Failed searches
are distinguished from completed zero-match searches; limited/failed searches
cannot infer a unique target. File/directory choices are capped at ten and
Spotify choices at five, with incomplete sets identified in the panel. Spotify
no-match results retain existing statuses and add local-only empty candidate
metadata. Choices preserve play versus open and the original action identity.
An explicit file-search `open_unique` intent retains the existing discovery
stage and creates a new-ID local `files.open` request; selecting its target
still requires its scoped grant and separate confirmation.

Unrelated ordinary conversation leaves the lease pending. A new explicit action
supersedes it, including a rejected compound native request. Only exact bounded
choice/catalog replies or trusted panel answers attach to it. Arbitrary composer
prose remains ordinary chat; the panel is the answer surface for free-text
parameters. Recognized stale replies do not fall through into provider chat.
Private path replies and explicit path-containing requests cannot fall through
to classification prompts. Provider absolute, drive-relative, UNC and rooted
paths, file URIs, encoded representations, Unicode normalization variants,
dot segments and mixed separators are rejected before alias normalization or
resolution. Composer detection may decode for recognition only; executable
targets are never created by decoding. Alias collisions disable the mapping
rather than select a root. Approved-root enforcement remains downstream.

The shared controller synchronously pauses an active Gemini worker before any
local or provider clarification question becomes actionable, including unknown
root aliases and private search candidates. Queued
audio rechecks the pause flag. The affected tool turn cannot commit to canonical
history or memory; provider-carried/spoken answers cannot resolve the lease.
The paused transport closes when that turn completes. Restart requires an
explicit user action after the local answer; it is never automatic. Local
clarification can continue independently of the closed provider tool turn.

Resolved requests re-enter existing validation and grant checks with
`confirmed=False`. Only a subsequent `CONFIRMATION_REQUIRED` result can cause
the trusted caller to issue a separate 60-second confirmation lease. A repeated
issuance while that lease is active does not renew it. Consumption verifies
identity/nonce, epoch, normalized arguments and deadline atomically, then the
existing action service rechecks validation and permissions before execution.
Revocation invalidates leases synchronously; late results and stale dialogs
cannot revive them. Stop/cancel, New/Clear Chat, configuration changes and app
shutdown also invalidate them. Global action idempotency remains unchanged.

Both native transports attach opaque batch identity, count and index. All
compound batches are rejected before dispatching any member; no prefix executes.
Unbound JSON clarification topics contain no operation, so they cannot safely
create a continuation. The shared local panel requests a new explicit action
instead of inventing an operation from a provider topic. This is a deliberate
fail-closed boundary, not a second clarification system.

Questions, answers, candidate payloads and pending leases have no persistence,
summary, memory, provider-prompt, Notification Center or ordinary-log route.
Lifecycle evidence contains only opaque IDs, action category, reason code,
monotonic timestamps and outcome. Existing finalized action audits retain their
normal local execution evidence without recording clarification dialogue.
No migration, credential surface, shell/elevation/file-mutation capability,
new command/action/permission/notification system, or Phase 13C+ utility is added.

## Historical implementation verification (superseded by correction results below)

New tests cover readiness/missing parameters, zero/multiple matches, exact
operation preservation, cancellation, absolute expiry, partial revision,
nonrenewal, supersession, unrelated conversation, stale/wrong/replayed answers,
concurrent consumption, provider self-answer rejection, cloud pause ordering,
trusted local open-any, path/alias attacks, revocation with the real SQLite
permission repository, confirmation expiry/mutation/replay, compound transport
and worker behavior, privacy surfaces, failed/truncated discovery, and
uncertain-time contracts without registering or executing a utility.

Existing positive provider-flow fixtures now use approved aliases instead of
forbidden absolute provider paths. Their permission, confirmation, local-result
and sanitization assertions are retained. The correction pass replaces the
disconnected privacy test with a regression through actual application wiring.

Commands from the repository root (Python 3.13 virtual environment):

```powershell
.\.venv313\Scripts\python.exe -m unittest tests.unit.services.test_action_clarification tests.unit.services.test_phase13b_integration tests.unit.ui.test_phase13b_proposal_flows tests.unit.services.test_provider_action_dispatcher tests.unit.services.test_provider_action_proposal_gateway tests.unit.ui.test_ollama_tool_worker tests.unit.ui.test_hosted_live_session_worker tests.unit.ui.test_assistant_tool_worker -q
.\.venv313\Scripts\python.exe -m unittest discover tests -q
.\.venv313\Scripts\python.exe -m ruff check project_akiha tests
.\.venv313\Scripts\python.exe -m black --check project_akiha tests
.\.venv313\Scripts\python.exe -m compileall -q project_akiha tests
.\scripts\smoke_source_app.ps1 -PythonExe (Resolve-Path '.\.venv313\Scripts\python.exe').Path -SmokeRoot (Join-Path $PWD 'dist\smoke-phase13b-verified') -StartupSeconds 8 -ShutdownSeconds 3
git diff --check
```

| Check | Final result |
| --- | --- |
| Focused new/integration/related regressions | 91 tests passed |
| Full unittest discovery | 1,743 tests run; OK (skipped=3: existing symlink tests) |
| Ruff | All checks passed |
| Black | 539 files unchanged |
| Compileall | Exit 0 |
| Source smoke | Startup/database/log checks passed; harness force-stopped background app |
| Whitespace diff | Exit 0 |

The three existing symlink tests are skipped because this Windows user cannot
create directory symlinks. No tests are changed to remove that restriction.
The smoke harness reports `CloseMainWindowRequested=False`, `ForcedStop=True`,
and child exit code `-1`; the harness itself exits 0. It verifies startup,
existing schema and smoke-log integrity, not graceful desktop shutdown.

Live provider accounts/audio devices, graceful interactive shutdown and the
manual packaged acceptance checklist have not been exercised. A fresh release
package was not built: this source implementation awaits independent audit and
owner acceptance. Existing packaged binaries cannot validate these new changes.
Before acceptance, verify real chat/voice questions, cloud microphone suspension
and explicit restart, revocation during dialogs, Stop/New/Clear Chat, and
shutdown on the desktop. Rerun the skipped symlink cases in an environment that
supports symlinks. Uncertain time expressions remain contracts only. The phase
closure checklist stays unchecked and 13C remains inactive. No commit or push
was created.

## Phase 13B implementation manifest

- `README.md`
- `docs/README.md`
- `docs/phases/phase-08-actions/BACKLOG.md`
- `docs/phases/phase-08-actions/README.md`
- `docs/phases/phase-13-assistant-utilities/PHASE13B.md`
- `docs/phases/phase-13-assistant-utilities/README.md`
- `docs/reference/CODEBASE_STRUCTURE.md`
- `docs/reference/LOCAL_DATA_PRIVACY.md`
- `docs/reference/SECURITY_REVIEW.md`
- `project_akiha/app/action_clarification_controller.py`
- `project_akiha/app/hosted_conversation_runtime.py`
- `project_akiha/app/main.py`
- `project_akiha/core/actions/clarification.py`
- `project_akiha/core/actions/path_input.py`
- `project_akiha/core/actions/registry.py`
- `project_akiha/core/voice_session/models.py`
- `project_akiha/integrations/spotify/albums.py`
- `project_akiha/integrations/spotify/playback.py`
- `project_akiha/integrations/spotify/playlists.py`
- `project_akiha/integrations/spotify/tracks.py`
- `project_akiha/providers/ai/ollama_provider.py`
- `project_akiha/providers/live/gemini.py`
- `project_akiha/providers/live/google_transport.py`
- `project_akiha/services/action_clarification.py`
- `project_akiha/services/assistant_actions.py`
- `project_akiha/services/assistant_permissions.py`
- `project_akiha/services/provider_action_dispatcher.py`
- `project_akiha/services/provider_action_proposal_gateway.py`
- `project_akiha/ui/action_clarification_panel.py`
- `project_akiha/ui/assistant_tool_worker.py`
- `project_akiha/ui/hosted_live_session_worker.py`
- `project_akiha/ui/ollama_tool_worker.py`
- `tests/unit/services/test_action_clarification.py`
- `tests/unit/services/test_phase13b_integration.py`
- `tests/unit/services/test_phase13b_corrections.py`
- `tests/unit/services/test_provider_action_dispatcher.py`
- `tests/unit/services/test_provider_action_proposal_gateway.py`
- `tests/unit/ui/test_hosted_live_session_worker.py`
- `tests/unit/ui/test_phase13b_proposal_flows.py`

## Audit correction pass — 2026-10-06

The complete independent audit and each cited implementation location were
reviewed before editing. Only verified Phase 13B acceptance defects were changed.
The preceding 91/1,743-test record is historical, not this pass's final result.
Phase 13B awaits another independent audit and owner acceptance; Phase 13C remains
inactive. No commit, push, phase completion or owner acceptance occurred.

| Audit finding / root cause | Correction |
| --- | --- |
| Incomplete requests did not advance ownership; late search results could replace newer questions and old confirmation remained usable | Claim each explicit request before readiness; supersede previous ownership atomically; gate result presentation, candidate publication and confirmation issuance on captured epoch and fingerprint |
| Same request ID retained old pending content despite changed arguments | Process-local complete normalized fingerprint bindings fail closed on changed action, source or arguments; trusted answers revise the binding; discovery-to-open continuation receives a new ID |
| Composer recognized only drive/UNC paths; slash-shaped private answers reached provider/export/SQLite | Detection-only recognition of Windows, UNC, POSIX, URI, encoded, mixed-separator and Unicode variants; route clarification answers before ordinary chat; arbitrary prose remains normal chat; free text stays on the local panel |
| Local questions did not suspend an already-active hosted worker | Shared controller invokes runtime suspension synchronously before publishing any question; worker latch drops queued and late audio; paused callbacks cannot start another turn; explicit fresh session only after ownership-aware completion/cancellation/expiry/supersession |
| Native path/alias checks ran after lossy alias normalization | Reject URI/encoded/absolute, traversal, dot segments, mixed separators and ambiguous normalization before resolver calls; preserve deterministic alias collision rejection and downstream approved roots |
| Privacy regression used disconnected mock surfaces | Replace it with the actual composer closure/signal, local panel, ChatController, provider-message construction, memory/summary entrypoints, exporter, logger capture and temporary SQLite repository; include a positive ordinary-chat control |

Fifteen new adversarial tests in `test_phase13b_corrections.py` cover all findings:
concurrent one-winner resolution/confirmation, exact deadlines and adjacent
microseconds, replay, stale results/issuance/publication, delayed question races,
changed request identities after resolution, fifteen private path variants,
resolver non-invocation across native lanes/actions, traversal aliases and
deterministic collision failure, local cloud pause ordering/audio drops, explicit
session restart and stale callbacks. The disconnected privacy method was replaced,
not counted as retained. Existing fixture IDs now distinguish different operations.

The connected privacy regression executes the production `submit_chat_message`
closure extracted by AST, avoiding full personal account/device startup. Real
Qt composer/panel signals, ChatController and SQLite storage are exercised. Hosted
audio-drop tests use the real worker; session terminal-callback tests use QObject
signal doubles with the real runtime and production suspension assignment. This
does not establish microphone/device/network acceptance.

### Exact correction-pass files (14)

- `docs/phases/phase-13-assistant-utilities/PHASE13B.md`
- `project_akiha/app/action_clarification_controller.py`
- `project_akiha/app/hosted_conversation_runtime.py`
- `project_akiha/app/main.py`
- `project_akiha/core/actions/path_input.py`
- `project_akiha/services/action_clarification.py`
- `project_akiha/services/provider_action_dispatcher.py`
- `project_akiha/services/provider_action_proposal_gateway.py`
- `project_akiha/ui/hosted_live_session_worker.py`
- `tests/unit/services/test_action_clarification.py`
- `tests/unit/services/test_phase13b_corrections.py`
- `tests/unit/services/test_phase13b_integration.py`
- `tests/unit/services/test_provider_action_proposal_gateway.py`
- `tests/unit/ui/test_phase13b_proposal_flows.py`

Unrelated concurrent migration/package stabilization changes, their tests, audit
documents and documentation-index edits were preserved. Complete-checkout test
counts include those changes; they are not part of this correction-pass manifest.

### Final commands and results

Commands ran from the repository root using `.venv313\Scripts\python.exe`.

```powershell
.\.venv313\Scripts\python.exe -B -m unittest tests.unit.services.test_phase13b_corrections tests.unit.services.test_action_clarification tests.unit.services.test_phase13b_integration tests.unit.ui.test_phase13b_proposal_flows tests.unit.services.test_provider_action_dispatcher tests.unit.services.test_provider_action_proposal_gateway tests.unit.ui.test_ollama_tool_worker tests.unit.ui.test_hosted_live_session_worker tests.unit.ui.test_assistant_tool_worker -q
.\.venv313\Scripts\python.exe -B -m unittest discover tests -q
.\.venv313\Scripts\python.exe -B -m ruff check --no-cache project_akiha tests
.\.venv313\Scripts\python.exe -B -m black --check project_akiha tests
.\.venv313\Scripts\python.exe -B -m compileall -q project_akiha tests
.\.venv313\Scripts\python.exe -B -m unittest discover -s tests/unit/core/actions -q
.\.venv313\Scripts\python.exe -B -m unittest tests.unit.services.test_assistant_actions tests.unit.services.test_assistant_permissions tests.unit.services.test_assistant_tool_gateway tests.unit.services.test_event_logger tests.unit.database.test_migrator tests.unit.app.test_shutdown tests.unit.app.test_conversation_runtime_router -q
.\scripts\smoke_source_app.ps1 -PythonExe (Resolve-Path '.\.venv313\Scripts\python.exe').Path -SmokeRoot (Join-Path $PWD 'dist\smoke-phase13b-corrections-final') -StartupSeconds 8 -ShutdownSeconds 3
git diff --check
```

| Check | Correction-pass result |
| --- | --- |
| Focused Phase 13B | 105 tests; OK; exit 0 |
| New adversarial regressions | 15 tests (included above) |
| Full single-process discovery | FAIL: abnormal native exit without unittest totals; verbose/faulthandler reproduction aborts in `test_tool_task_failure_stops_visibly_instead_of_stranding_turn` while processing Qt events |
| Complete suite in separate package processes | 1,759 tests total; all ten packages OK; three existing symlink skips; exit 0. This does not replace the failed single-process gate |
| Ruff | All checks passed; exit 0 |
| Black check | 541 files unchanged; exit 0 |
| Compile/static syntax | compileall exit 0 |
| Static core import boundaries | AST checks for `clarification.py` and `path_input.py`: no Qt, database, app, provider, service or UI imports; exit 0 |
| Core action boundaries | 65 tests; OK; skipped=3 Windows symlink cases; exit 0 |
| Additional action/permission/tool/log/database/shutdown/runtime gates | 88 tests; OK; exit 0 |
| Source/database/log smoke | 15 expected tables; log OK; harness exit 0 |
| git diff --check | Exit 0 |

Complete package coverage was run with:

```powershell
foreach ($auditPackage in @('app','config','core','database','integrations','providers','scripts','services','spikes','ui')) {
  & .\.venv313\Scripts\python.exe -B -m unittest discover -s "tests/unit/$auditPackage" -q
}
```

Package totals: app 430, config 26, core 265 (three skips), database 83,
integrations 156, providers 159, scripts 4, services 414, spikes 22, UI 200.

The full suite abort remains a validation blocker. It must not be presented as
a pass or silently skipped. Diagnostic discovery without the new correction
module passed 1,744 tests (three skips); excluding its hosted correction class
passed 1,756; excluding only its explicit-restart/stale-session simulation passed
1,758. The full UI package alone passed 200 tests. Attempts at explicit Qt object
cleanup, weak owner callbacks, session doubles and child-process isolation did
not establish a passing full single-process run. No production root cause or
pre-existing status is proved for this abort. Failed attempts were retained in
the audit record, not treated as acceptance evidence.

### Shutdown investigation and remaining acceptance

The unchanged smoke harness reported process 15420,
`CloseMainWindowRequested=False`, `ForcedStop=True`, child exit `-1`. Startup,
schema and logs passed, but graceful shutdown was not proved. HEAD already keeps
the tray app alive after closing windows; Phase 12's manual report explicitly
records forced harness cleanup because the harness cannot operate the tray menu.
This forced smoke result is pre-existing/harness behavior, not evidence of a
Phase 13B regression. No shutdown expansion was made.

Remaining checks: resolve the full-suite Qt abort; normal clarification in the
actual desktop UI; cancel/timeout/supersession/revocation during real dialogs;
Gemini Live microphone suspension and explicit resumption with a live provider;
graceful application shutdown with a pending lease; a fresh packaged-build smoke
test; three symlink tests in a supported environment; another independent audit
and owner acceptance. No packaged release was built or approved in this pass.

## Final correction pass after the second independent audit — 2026-10-06

The complete second audit in the implementation conversation was read before
editing. Its remaining defects were reproduced independently against the current
working tree. The earlier correction-pass results above remain historical; this
section records the final correction pass. Phase 13B still awaits another
independent audit and owner acceptance. Phase 13C remains inactive.

### Reproduced causes and exact corrections

| Item | Before editing | Final correction |
| --- | --- | --- |
| Atomic publication | A barrier paused an old file-search result immediately after its ownership check. Accepting a newer incomplete application action during that gap resulted in the old result replacing the newer question. | The controller retains the captured epoch. `publish_result` checks the exact epoch and normalized request identity under the service RLock and installs its continuation without releasing that lock. Explicit-epoch `begin` also checks request identity. Hosted suspension occurs only after ownership validation, before publication; ownership is checked again after the callback to cover synchronous reentrant action acceptance. UI refresh follows publication. |
| Clarification privacy | The three audit examples with relative-path spaces or surrounding prose all returned false from path detection; the second audit had demonstrated their actual composer/provider/persistence leakage. | File/directory foreground clarification routing uses detection-only embedded-path recognition before ordinary chat. Quoted, Windows/UNC, POSIX, URI, encoded, mixed-separator and relative paths containing spaces are rejected locally. Decoded strings never become execution arguments. Plain conversation, A/B discussion and HTTP-link conversation remain ordinary chat. |
| Alias matching | `.Downloads`, `Downloads;folder` and `Downloads#folder` were accepted and resolved to the approved Downloads root. | Alias keys only trim ASCII outer spaces and casefold, with bounded lengths and strict syntax. Leading dots, punctuation, controls, normalization tricks and appended words cannot become an approved alias. Invalid inputs are rejected before local argument resolution. Safe descendants still require an exact configured root alias; unknown safe names remain untrusted local clarification material. Duplicate/case-conflicting configured keys fail even when their paths agree. No fuzzy selection was added. |
| Hosted regression accuracy | The existing restart simulation reached `hosted_transcript_commit_failed`, then satisfied its inactive assertion through error shutdown. | The session double implements paused/noncanonical turns and the transcript commit method is a valid AsyncMock. Assertions require noncanonical cancellation, `clarification_pending`, no canonical commit, no error notification, an explicit new session, and no stale callback effects or unexpected stop of the newer worker. |
| Qt lifecycle | The exact two-test order reproduced a native access violation before editing. The second audit observed BehaviorHistoryWindow destruction on a worker GC thread and reproduced the controlled failure using the HEAD hosted worker. | Classified as pre-existing. Every behavior-history test window now has GUI-thread close/deleteLater/deferred-deletion cleanup. QMessageBox mock call history is reset to release its parent reference. A destruction-thread regression verifies C++ deletion on the GUI thread. Hosted worker tests register cleanup before start, request stop, assert join, and perform deferred deletion on the owning thread. No shared global Qt teardown, GC disabling, crash suppression or suite splitting was used as the solution. |

A further probe during correction reproduced reentrant ownership loss when the
audio suspension callback synchronously accepted a newer request. The final
identity regression includes this case; the post-callback validation rejects the
old publication without replacing the newer pending request.

### Connected privacy evidence

The production composer closure and real ChatWindow/panel signals are connected
to the real ChatController and a temporary SQLiteConversationRepository. The
previous memory AsyncMock was replaced with the production MemoryPipeline,
default heuristic extraction/validation and SQLiteMemoryRepository. Export and
provider-message construction use the real ChatController paths; default
heuristic summaries are persisted and checked in SQLite.

The same test surface now has a real EventBus/EventLogger, an
IntegrationNotificationCoordinator using SQLite external-event and notification
repositories, and ProactiveDeliveryController/QtProactiveDeliverySurface. Positive
controls save an ordinary preference into memory and summaries and deliver a
synthetic external notification through that bus into the UI/inbox/logging route.
Those controls establish that the checked surfaces are operational, rather than
empty disconnected objects. All database tables, exports, provider inputs, event
payloads, captured production logs, memories and UI history are checked for the
synthetic secret. Both pending file and directory commands receive the path
matrix; unrelated conversation preserves the pending owner while reaching chat.

This is connected production-closure/object testing without personal account,
device or network startup. It is not interactive desktop or live-microphone
acceptance.

### Added and strengthened regressions

Four new test methods were added:

- `CorrectionOwnershipTest.test_barrier_new_action_wins_between_owner_check_and_publication`
- `CorrectionOwnershipTest.test_atomic_publication_requires_exact_request_identity`
- `CorrectionProviderPathTest.test_alias_only_trims_spaces_and_casefolds`
- `BehaviorHistoryWindowTest.test_window_cleanup_destroys_on_gui_thread`

The correction module now contains 18 tests. Its connected privacy method,
native-path rejection matrix, alias-conflict cases, ordinary-chat controls and
hosted restart test were strengthened. The gateway's two formerly fuzzy
`Downloads folder` fixtures now use the explicitly allowed exact alias with outer
spaces. Existing expiry, concurrency, replay, permission and boundary tests were
retained. The total increased from 1,759 to 1,763 without adding skips.

### Exact files changed by this final pass (9)

- `docs/phases/phase-13-assistant-utilities/PHASE13B.md`
- `project_akiha/app/action_clarification_controller.py`
- `project_akiha/core/actions/path_input.py`
- `project_akiha/services/action_clarification.py`
- `project_akiha/services/provider_action_proposal_gateway.py`
- `tests/unit/services/test_phase13b_corrections.py`
- `tests/unit/services/test_provider_action_proposal_gateway.py`
- `tests/unit/ui/test_behavior_history_window.py`
- `tests/unit/ui/test_hosted_live_session_worker.py`

The behavior-history test is an additional file beyond the earlier 39-file
implementation manifest. The separately documented Phases 1–12 migration/package
stabilization source, tests and audit/index documents were preserved unchanged.
There were no new executors, tools, migrations or Phase 13C+ functionality.

### Final validation commands and results

Commands ran from the repository root with `PYTHONDONTWRITEBYTECODE=1`.

```powershell
for ($qtAuditRepeat = 1; $qtAuditRepeat -le 10; $qtAuditRepeat++) {
  & .\.venv313\Scripts\python.exe -B -m unittest tests.unit.ui.test_behavior_history_window.BehaviorHistoryWindowTest.test_clear_matching_emits_selected_filters_after_confirmation tests.unit.ui.test_hosted_live_session_worker.HostedLiveSessionThreadTest.test_tool_task_failure_stops_visibly_instead_of_stranding_turn -q
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
.\.venv313\Scripts\python.exe -B -m unittest tests.unit.services.test_phase13b_corrections -v
.\.venv313\Scripts\python.exe -B -m unittest tests.unit.services.test_phase13b_corrections tests.unit.services.test_action_clarification tests.unit.services.test_phase13b_integration tests.unit.ui.test_phase13b_proposal_flows tests.unit.services.test_provider_action_dispatcher tests.unit.services.test_provider_action_proposal_gateway tests.unit.ui.test_ollama_tool_worker tests.unit.ui.test_hosted_live_session_worker tests.unit.ui.test_assistant_tool_worker -q
.\.venv313\Scripts\python.exe -B -m unittest discover tests -q
foreach ($auditPackage in @('app','config','core','database','integrations','providers','scripts','services','spikes','ui')) {
  & .\.venv313\Scripts\python.exe -B -m unittest discover -s "tests/unit/$auditPackage" -q
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
.\.venv313\Scripts\python.exe -B -m unittest discover -s tests/unit/core/actions -q
.\.venv313\Scripts\python.exe -B -m unittest tests.unit.services.test_assistant_actions tests.unit.services.test_assistant_permissions tests.unit.services.test_assistant_tool_gateway tests.unit.services.test_event_logger tests.unit.database.test_migrator tests.unit.app.test_shutdown tests.unit.app.test_conversation_runtime_router -q
.\.venv313\Scripts\python.exe -B -m ruff check --no-cache project_akiha tests
.\.venv313\Scripts\python.exe -B -m black --check project_akiha tests
.\scripts\smoke_source_app.ps1 -PythonExe (Resolve-Path '.\.venv313\Scripts\python.exe').Path -SmokeRoot (Join-Path $env:TEMP 'akiha-phase13b-final-correction-smoke') -StartupSeconds 8 -ShutdownSeconds 3
git diff --check
```

Compilation and static boundaries used this command, without bytecode writes:

```powershell
@'
import ast,pathlib
files=sorted(p for root in ('project_akiha','tests') for p in pathlib.Path(root).rglob('*.py'))
for p in files:
    compile(p.read_bytes(),str(p),'exec')
for name in ('clarification.py','path_input.py'):
    p=pathlib.Path('project_akiha/core/actions')/name
    for node in ast.walk(ast.parse(p.read_text(encoding='utf-8'))):
        modules=([node.module or ''] if isinstance(node,ast.ImportFrom) else [x.name for x in node.names] if isinstance(node,ast.Import) else [])
        for module in modules:
            assert not module.startswith(('PySide6','sqlite3','project_akiha.app','project_akiha.database','project_akiha.providers','project_akiha.services','project_akiha.ui')),(str(p),module)
print('Compiled',len(files),'files in memory; static core boundaries PASS')
'@ | .\.venv313\Scripts\python.exe -B -
```

| Gate | Final result |
| --- | --- |
| Exact two-test Qt reproducer | 10 consecutive normal runs, 2 tests each, OK, exit 0; repeated after final worker teardown changes |
| Correction module | 18 tests, OK, exit 0 |
| Focused Phase 13B | 108 tests, OK, exit 0 |
| Required single-process full discovery | **1,763 tests in 24.204 seconds; OK (skipped=3); normal exit 0 with final unittest totals** |
| Package-separated discovery (supplemental only) | 1,763 tests across ten packages; all OK; 3 existing symlink skips; exit 0 |
| Action boundaries | 65 tests, OK (skipped=3), exit 0 |
| Security/action/permission/log/database/shutdown/runtime selection | 88 tests, OK, exit 0 |
| Ruff | All checks passed, exit 0 |
| Black check | 541 files unchanged, exit 0 |
| Compilation/static boundaries | 541 files compiled in memory; forbidden core imports absent; exit 0 |
| Source/database/log smoke | All 15 expected tables and log checks passed; harness exit 0 |
| git diff --check | Exit 0; existing LF/CRLF conversion warnings only |

Package totals: app 430, config 26, core 265, database 83, integrations 156,
providers 159, scripts 4, services 417, spikes 22, UI 201. The three skips are the
existing Windows symlink cases. Expected negative-test diagnostics appeared; the
single-process run ended with unittest totals rather than a native abort.

### Shutdown, packaging and remaining acceptance

The source smoke reported PID 24964, `CloseMainWindowRequested=False`,
`ForcedStop=True`, child exit `-1`. Startup/schema/log checks passed;
**graceful process shutdown was not proved**. The known tray/harness limitation
remains pre-existing. Unit shutdown/lease tests are narrower evidence, not manual
shutdown acceptance with a real pending lease.

Remaining manual checks are normal clarification in the actual desktop UI;
cancel/timeout/supersession/permission revocation in real dialogs; Gemini Live
microphone suspension and successful explicit resumption with a live provider;
graceful application shutdown while a lease is pending; three symlink cases in a
supported environment; and a fresh packaged-build smoke after the separately
identified destructive WorkDir cleanup guard is fixed. No clean packaged build
was run, and that guard was not changed in this correction pass.

Another independent audit and owner acceptance remain required. No commit, push,
phase completion, owner acceptance or Phase 13C authorization occurred.

## Bounded composition-boundary correction — 2026-10-07

Status remains **awaiting independent audit and owner acceptance**.

### Reproduction and architectural cause

The latest independent audit was read before editing. The independent composed
probe was rerun before this pass using:
`python.exe -B "$env:TEMP\akiha_final_readonly_probe.py"` (exit 0).
It reproduced F1–F3: directory and media zero/multiple/limited-single results
raised stale-ownership errors instead of publishing; unique callbacks accepted
fresh ownership after a barrier admitted a newer incomplete action, clearing its
clarification; composer inputs `I prefer Downloads/ SPACE_SECRET.mp3` and
`I prefer %2525252FENCODED_SECRET.mp3` reached canonical/provider/SQLite/export/
summary and real memory surfaces.

The shared central publication correction was intact, but local search bypassed
its ownership model: callbacks held only an epoch, created new request identities
for clarification, and used ordinary execution admission for unique results.
The privacy detector also assumed tightly joined path segments and shallow
encoding. Existing connected tests did not include these composition cases.

### Typed continuation and privacy correction

Both local search flows now capture a frozen `LocalSearchIdentity` before worker
startup. It binds the epoch, complete normalized request fingerprint, request and
action IDs, source, fixed operation, generation, nonce, creation ID/time and exact
120-second deadline. Search roots are bound by their digest, along with every
search argument. Immutable request parameters prevent later mutation.

Every result shape passes through `continue_local_search` under the service's
owner lock. Its typed outcomes are stale, clarification required, ready to
execute, or rejected. It validates the entire captured identity, expiry and all
candidates, then consumes discovery once. Zero/multiple/limited results publish
under the captured owner; unique results produce a trusted revision of that same
request, preserving its IDs and epoch. Neither callback claims ownership or
creates an unrelated request. Suspension hooks are followed by an ownership
recheck to handle synchronous reentry. Execution enqueue consumes ready admission
under the same lock, and the action worker checks captured ownership again before
dispatch. Supersession, revocation, cancellation, timeout, changed fingerprints,
duplicate results and late failures cannot restore consumed authority. Approved
root enforcement remains downstream in the existing executor policy.

During file/directory clarification, slash or backslash anywhere, path-shaped
filenames, drive/UNC/URI/dot syntax, malformed encoding and encoded path material
stay local. Detection normalizes Unicode/whitespace and repeatedly decodes for
detection only, with a 4,096-character input bound and maximum eight decoding
steps. Suspicious encoding left at the bound is rejected; decoded text is never
used for resolution or execution. The panel presents a fixed privacy-safe notice
without persisting the rejected input. Plain unrelated conversation still reaches
chat and does not supersede the pending clarification.

The panel's deliberate **Continue as normal chat** button uses the exact current
lease identity and reads only the current Qt composer synchronously. It explicitly
tells the user that this text will be saved and sent. It neither arms a later
message override nor invokes action routing. Provider/voice submissions cannot
select this local control; stale controls cannot authorize a newer lease.

### Connected regressions and exact files

New `Phase13BCompositionTest` methods in
`tests/unit/app/test_phase13b_composition.py`:

- `test_zero_multiple_limited_and_unique_share_captured_ownership`
- `test_barrier_supersession_before_publication_all_result_shapes`
- `test_barrier_supersession_after_publication_all_result_shapes`
- `test_barrier_supersession_immediately_before_execution_enqueue`
- `test_reentrant_supersession_during_suspension_hook`
- `test_revocation_during_search_rejects_every_result_shape`
- `test_cancellation_during_search_rejects_every_result_shape`
- `test_duplicate_and_late_results_and_failures_cannot_change_state`
- `test_exact_search_timeout_boundaries_for_all_shapes`
- `test_complete_fingerprint_generation_nonce_and_creation_are_bound`
- `test_ready_admission_is_single_use_and_expires_before_enqueue`
- `test_worker_rechecks_owner_before_dispatching_queued_unique_result`
- `test_rejected_result_is_typed_and_cannot_be_replayed`
- `test_connected_privacy_rejects_all_material_on_every_real_surface`
- `test_trusted_local_button_sends_only_current_composer_as_chat`
- `test_stale_normal_chat_button_cannot_override_new_owner`

Tests instantiate the actual `_run_application` composition with temporary local
data, real Qt composer/panel signals, ChatController, SQLite repositories, memory
extraction and summary persistence, exports, notification delivery, EventBus/
EventLogger and production file logging. Controlled search workers provide real
Qt result signals, while barrier hooks exercise the actual composed callbacks.
The recording mock provider keeps tests offline and inspects actual provider
messages. Positive controls persist ordinary memory/summary and deliver a real
synthetic notification. The privacy matrix covers both pending operations, 20
nested encoding variants, spaces/prose, mixed/Unicode separators, malformed
encoding and oversized input. All SQLite tables and connected output surfaces
are scanned; no private sentinel appears. Candidate rejection covers empty,
control-character and oversized paths for directory and media operations.

Test graph startup timers are bound to a QObject context, then canceled by GUI
thread destruction after shutdown. Workers are joined, queued signals processed
while widgets remain alive, deferred deletion processed, mock references cleared
and production log handlers closed. Garbage collection remains enabled. The
existing correction module retains 18 tests; its A/B and HTTP-path fixtures now
assert local rejection under the explicitly stricter slash policy. No tests were
disabled, duplicated, skipped or removed.

Exact files changed by this pass (10):

- `docs/phases/phase-13-assistant-utilities/PHASE13B.md`
- `project_akiha/app/main.py`
- `project_akiha/app/action_clarification_controller.py`
- `project_akiha/core/actions/clarification.py`
- `project_akiha/core/actions/path_input.py`
- `project_akiha/services/action_clarification.py`
- `project_akiha/ui/action_clarification_panel.py`
- `project_akiha/ui/assistant_action_worker.py`
- `tests/unit/services/test_phase13b_corrections.py`
- `tests/unit/app/test_phase13b_composition.py` (new)

All other existing dirty files were preserved against the pre-pass SHA-256
snapshot. Central publication, confirmation invalidation, strict alias matching,
fingerprint enforcement, Gemini suspension/restart and the pre-existing Qt fix
remain covered. Migration/package stabilization files were unchanged. There are
no new executors, tools, migrations or Phase 13C+ features.

### Exact validation commands and results

Commands ran from the repository root using `.venv313`, `-B`, and no bytecode
writes. The prior correction record's compilation/static command was rerun
unchanged (542 files now, rather than 541). All final gates exited 0:

```powershell
.\.venv313\Scripts\python.exe -B -m unittest tests.unit.app.test_phase13b_composition tests.unit.services.test_phase13b_corrections -q
.\.venv313\Scripts\python.exe -B -m unittest tests.unit.app.test_phase13b_composition -q
.\.venv313\Scripts\python.exe -B -m unittest tests.unit.app.test_phase13b_composition.Phase13BCompositionTest.test_connected_privacy_rejects_all_material_on_every_real_surface -q
.\.venv313\Scripts\python.exe -B -m unittest tests.unit.app.test_phase13b_composition tests.unit.services.test_phase13b_corrections tests.unit.services.test_action_clarification tests.unit.services.test_phase13b_integration tests.unit.ui.test_phase13b_proposal_flows tests.unit.services.test_provider_action_dispatcher tests.unit.services.test_provider_action_proposal_gateway tests.unit.ui.test_ollama_tool_worker tests.unit.ui.test_hosted_live_session_worker tests.unit.ui.test_assistant_tool_worker -q
.\.venv313\Scripts\python.exe -B -m unittest discover tests -q
for ($qtAuditRepeat = 1; $qtAuditRepeat -le 10; $qtAuditRepeat++) {
  & .\.venv313\Scripts\python.exe -B -m unittest tests.unit.ui.test_behavior_history_window.BehaviorHistoryWindowTest.test_clear_matching_emits_selected_filters_after_confirmation tests.unit.ui.test_hosted_live_session_worker.HostedLiveSessionThreadTest.test_tool_task_failure_stops_visibly_instead_of_stranding_turn -q
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
.\.venv313\Scripts\python.exe -B -m unittest discover -s tests/unit/core/actions -q
.\.venv313\Scripts\python.exe -B -m unittest tests.unit.services.test_assistant_actions tests.unit.services.test_assistant_permissions tests.unit.services.test_assistant_tool_gateway tests.unit.services.test_event_logger tests.unit.database.test_migrator tests.unit.app.test_shutdown tests.unit.app.test_conversation_runtime_router -q
.\.venv313\Scripts\python.exe -B -m ruff check --no-cache project_akiha tests
.\.venv313\Scripts\python.exe -B -m black --check project_akiha tests
.\scripts\smoke_source_app.ps1 -PythonExe (Resolve-Path '.\.venv313\Scripts\python.exe').Path -SmokeRoot (Join-Path $env:TEMP ('akiha-13b-composition-' + [guid]::NewGuid().ToString('N'))) -StartupSeconds 8 -ShutdownSeconds 3
git diff --check
```

| Gate | Result |
| --- | --- |
| New composition + previous corrections | 34 tests, OK; composition separately 16 tests, OK |
| Connected privacy selection | 1 test, OK; synthetic sentinels absent on all checked surfaces |
| Focused Phase 13B including composition | 124 tests in 8.509 seconds, OK |
| Required single-process discovery | **1,779 tests in 29.170 seconds; OK (skipped=3); exit 0 with final totals** |
| Historical Qt pair | 10/10 consecutive runs, 2 tests each, OK |
| Action boundaries | 65 tests, OK (3 existing symlink skips) |
| Security/action/permissions/database/log/shutdown/runtime | 88 tests, OK |
| Ruff | All checks passed |
| Black | 542 files unchanged |
| Compilation/static core boundaries | 542 files compiled in memory; forbidden imports absent |
| Source/database/log smoke | 15 required tables and production log checks passed; harness exit 0 |
| git diff --check | Exit 0; existing LF/CRLF warnings only |

The initial lint run found import ordering, unused test imports, long strings and
a loop closure binding; those were corrected before the final passing run.
Intermediate new tests also exposed bare-filename detection and fixture timer/
SQLite teardown gaps, which were corrected before the final complete suite.

### Remaining acceptance and shutdown limits

Source smoke PID 24024: `CloseMainWindowRequested=False`, `ForcedStop=True`,
child exit `-1`. **Graceful shutdown remains unproved**; unit shutdown and joined
test-worker evidence do not establish real desktop shutdown with a pending lease.
The prior pre-existing Qt classification and stabilization record remain intact.

Manual checks remain: actual desktop clarification and the explicit ordinary-chat
control; cancellation/timeout/supersession/revocation; live Gemini microphone
suspension and explicit restart; graceful shutdown while a lease is pending;
the three environment-dependent symlink cases; packaged smoke only after the
separately identified destructive WorkDir cleanup guard is fixed. No packaging
was run or guard change attempted. No commit, push, phase completion, owner
acceptance or Phase 13C work occurred. Another independent audit is required.

## Bounded incomplete-action usability correction — 2026-10-07

Status remains **awaiting independent audit and owner acceptance**. This record
adds local target selection to the existing Phase 13B contract; it does not
activate Phase 13C or record acceptance.

### Reproduced cause and correction

Exact typed/local-voice `Open an app.` and `Open a folder.` already preserved
`applications.launch` and `files.open_directory`, respectively. Their missing
target leases had no candidate catalog, so the panel offered free text. The
manual folder reproduction supplied `Downloads` as the `path` parameter, which
correctly failed absolute-path validation with “Akiha refused an invalid
assistant action request.” Name-prefixed incomplete wording could instead reach
the provider JSON fallback; an unbound CLARIFY topic correctly produced the
generic exact-target notice with Cancel alone. Choice rendering itself worked
when an existing search had supplied candidates.

The composed application now supplies a bounded, immutable local target
snapshot only for locally parsed chat-source missing application/folder targets:

- Applications come from the existing trusted ApplicationCatalog, filtered for
  current availability and an active application launch grant. No catalog entry
  or permission is invented or automatically granted.
- Folder candidates come from configured approved roots with open permission
  and current availability. Existing deterministic alias-conflict rejection is
  retained. The dropdown displays only root basenames; its item data contains a
  random opaque choice ID, never a root, path, or alias interpreted as a path.
- Snapshots retain the original request/action ID, source and operation. They
  publish through the existing atomic owner-bound `begin` operation. There are
  at most ten candidates; larger sets are marked bounded/incomplete.
- Only the dedicated LOCAL_UI selection can resolve an opaque ID. IDs bind to
  the pending lease; arbitrary IDs, ordinal/text/provider/voice answers, mixed
  answer fields and “open any” cannot resolve these catalog choices. Existing
  cancel handling remains available.
- Resolution rechecks current catalog availability and permission eligibility
  under the lease synchronization boundary. Removal, revocation, exact expiry,
  replay and supersession fail closed. Resolution retains the original owner
  epoch when enqueueing and the worker checks that owner before dispatch; an
  older selection cannot claim fresh ownership after a newer action.
- The resolved canonical path/application ID continues through the existing
  action validator, scoped permission policy and confirmation handling. These
  two existing action definitions use `ConfirmationPolicy.NEVER`; this pass
  changes neither that policy nor the confirmation lease machinery. Absolute
  paths and approved-root containment remain mandatory downstream. A standalone
  raw `Downloads` path still fails validation.

One anchored Akiha name prefix is now supported, including `Akiha, please …`
and `please Akiha, …`; the existing deterministic envelope still handles
courtesy and negation. Incomplete input is bounded to 2,000 characters. The
existing finite incomplete-command map is retained. Arbitrary prose and an
unbound provider CLARIFY topic do not acquire an invented operation.

When no eligible choices exist, the bound local panel directs the user to
configure/install an app with launch permission or configure a folder with open
permission in Settings. It hides the free-text answer and submit controls.
Catalog choices also hide free text and “open any.” Privacy-rejection guidance
refers to the picker or Settings rather than a hidden answer field. The trusted
ordinary-chat control and prior privacy detection remain unchanged.

### Exact correction manifest and new regressions

Files changed by this pass (7):

- `docs/phases/phase-13-assistant-utilities/PHASE13B.md`
- `project_akiha/app/main.py`
- `project_akiha/app/action_clarification_controller.py`
- `project_akiha/core/actions/clarification.py`
- `project_akiha/services/action_clarification.py`
- `project_akiha/ui/action_clarification_panel.py`
- `tests/unit/app/test_phase13b_usability.py` (new)

New `Phase13BUsabilityTest` methods (16):

- `test_typed_bare_and_bounded_name_courtesy_commands_have_choices`
- `test_local_voice_uses_the_same_bare_and_prefixed_picker`
- `test_manual_voice_downloads_alias_rejected_and_opaque_root_opens_twice`
- `test_application_choice_keeps_request_operation_and_dispatch_policy`
- `test_no_roots_shows_configuration_guidance_without_answer_field`
- `test_unavailable_and_ungranted_apps_are_not_offered`
- `test_removed_and_revoked_roots_fail_closed`
- `test_removed_and_revoked_apps_fail_closed`
- `test_exact_expiry_and_single_use_selection`
- `test_cancel_and_supersession_reject_old_opaque_selection`
- `test_opaque_choices_are_local_ui_only_and_bound_to_the_lease`
- `test_new_action_during_resolution_notification_wins_without_old_enqueue`
- `test_fingerprint_and_confirmation_guarantees_survive_choice_resolution`
- `test_unbound_provider_clarify_keeps_the_generic_cancel_only_notice`
- `test_arbitrary_prose_negation_and_repeated_prefixes_do_not_create_actions`
- `test_picker_paths_answers_and_ids_stay_out_of_connected_persistence`

The fixture reuses graph setup/teardown without inheriting or rediscovering old
test methods. Typed tests use the real composer; local-voice tests publish a
final transcript through the actual ChatVoicePresenter and voice submission
route. Catalog availability uses synthetic files in a temporary catalog.
Execution tests dispatch through the real action service, validator, permission
repository and policy; only the external desktop executor is mocked. The exact
Downloads reproduction is repeated twice, while the raw-alias action remains
denied. Post-selection revocation is also checked at the worker ownership guard
and downstream permission policy.

Connected privacy checks use synthetic sentinels, the actual ChatController,
temporary SQLite repositories, provider-message construction, transcript export,
real persisted memories and summaries, notification delivery, EventBus/EventLogger
and production application logs. Public conversation, memory, summary and
notification positive controls run. No private picker sentinel or choice ID
appears on conversation/provider/output surfaces. Configured roots necessarily
remain in `assistant_action_permissions`; the test explicitly verifies that this
is the only table containing the root sentinel, with no clarification copies.
No previous tests were edited, disabled, weakened, duplicated or skipped.

### Validation commands and results

All commands ran from the repository root with `.venv313` and `-B`. Final test,
lint, formatting, compilation/boundary and diff gates exited 0:

```powershell
.\.venv313\Scripts\python.exe -B -m unittest tests.unit.app.test_phase13b_usability -q
.\.venv313\Scripts\python.exe -B -m unittest tests.unit.app.test_phase13b_usability tests.unit.app.test_phase13b_composition tests.unit.services.test_phase13b_corrections tests.unit.services.test_action_clarification tests.unit.services.test_phase13b_integration tests.unit.ui.test_phase13b_proposal_flows tests.unit.services.test_provider_action_dispatcher tests.unit.services.test_provider_action_proposal_gateway tests.unit.ui.test_ollama_tool_worker tests.unit.ui.test_hosted_live_session_worker tests.unit.ui.test_assistant_tool_worker -q
.\.venv313\Scripts\python.exe -B -m unittest discover tests -q
for ($usabilityQtRepeat = 1; $usabilityQtRepeat -le 10; $usabilityQtRepeat++) {
  & .\.venv313\Scripts\python.exe -B -m unittest tests.unit.ui.test_behavior_history_window.BehaviorHistoryWindowTest.test_clear_matching_emits_selected_filters_after_confirmation tests.unit.ui.test_hosted_live_session_worker.HostedLiveSessionThreadTest.test_tool_task_failure_stops_visibly_instead_of_stranding_turn -q
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
.\.venv313\Scripts\python.exe -B -m unittest discover -s tests/unit/core/actions -q
.\.venv313\Scripts\python.exe -B -m unittest tests.unit.services.test_assistant_actions tests.unit.services.test_assistant_permissions tests.unit.services.test_assistant_tool_gateway tests.unit.services.test_event_logger tests.unit.database.test_migrator tests.unit.app.test_shutdown tests.unit.app.test_conversation_runtime_router -q
.\.venv313\Scripts\python.exe -B -m ruff check --no-cache project_akiha tests
.\.venv313\Scripts\python.exe -B -m black --check project_akiha tests
.\scripts\smoke_source_app.ps1 -PythonExe (Resolve-Path '.\.venv313\Scripts\python.exe').Path -SmokeRoot (Join-Path $env:TEMP ('akiha-13b-usability-' + [guid]::NewGuid().ToString('N'))) -StartupSeconds 8 -ShutdownSeconds 3
git diff --check
```

The in-memory compilation/static boundary command recorded above was rerun
unchanged: 543 files compiled; forbidden core imports absent.

| Gate | Final result |
| --- | --- |
| New composed usability tests | 16 tests in 5.613 seconds, OK, exit 0 |
| Focused Phase 13B including usability | 140 tests in 13.532 seconds, OK, exit 0 |
| Required single-process discovery | **1,795 tests in 35.093 seconds; OK (skipped=3); final totals and exit 0** |
| Historical Qt pair | 10/10 runs, 2 tests each, OK, exit 0 |
| Action boundaries | 65 tests, OK (3 existing symlink skips), exit 0 |
| Security/action/permissions/database/log/shutdown/runtime | 88 tests, OK, exit 0 |
| Ruff | All checks passed, exit 0 |
| Black | 543 files unchanged, exit 0 |
| Compilation/static boundaries | 543 files compiled in memory, PASS, exit 0 |
| Source/database/log smoke | 15 required tables and production log checks passed; harness exit 0 |
| git diff --check | Exit 0; existing LF/CRLF warnings only |

Initial new tests exposed fixture assumptions about Windows short TEMP paths,
the existing ActionStatus enum and JSON proposal schema; fixtures were corrected
to use canonical configured targets, `SUCCESS`, and the actual `action` schema.
Initial Ruff import-order/line-length findings were corrected before final gates.
These were test/lint corrections; no existing permission or path rule was relaxed.

### Scope and remaining manual acceptance

All 42 other pre-existing dirty/untracked files match their pre-pass SHA-256
snapshot. The separately documented Phases 1–12 stabilization changes, package/
migration changes, previous ownership/continuation, privacy, Gemini and Qt fixes
remain intact. There are no new tools, executors, migrations or Phase 13C features.

Source smoke PID 25492 had `CloseMainWindowRequested=False`, `ForcedStop=True`,
child exit `-1`. **Graceful shutdown remains unproved** despite passing source,
database and log checks. This pass makes no claim of live desktop acceptance.

Remaining owner checks include actual typed and microphone app/root selection;
cancel, timeout, supersession and permission revocation; Gemini audio suspension
and explicit restart; graceful shutdown with a pending lease; the three skipped
environment-dependent symlink cases. Packaged smoke remains pending until the
separately identified destructive WorkDir cleanup guard is fixed. No packaging,
commit, push, phase completion, owner acceptance or Phase 13C activation occurred.
Another independent audit and owner acceptance remain required.

## Local registered-music usability extension — 2026-10-07

Status remains **awaiting independent audit and owner acceptance**. The owner
requested a Music files Settings tab with drag-and-drop registration, chose
registration of existing locations rather than copying, and requested that
“Open a music file” offer all registered files in its dropdown. This is a local
usability extension of the existing `files.open` operation; it activates no
Phase 13C functionality and adds no provider tool, executor or migration.

### Cause and resulting behavior

There was no local registered-music catalog or Settings page. The exact
incomplete music command had no bound catalog, so a generic file clarification
could only request free text. The new immutable `MusicFilesConfig` retains
absolute path references in the private user TOML configuration, with paths
excluded from its repr. Dropping files or using Add files saves immediately.
Removing an entry removes its reference and leaves the source file in place.
Registration reads file metadata for safety/availability, never audio content;
it neither copies files nor grants permission. Supported extensions reuse the
existing passive-audio policy: MP3, WAV, FLAC, OGG and M4A.

The Settings page includes filename filtering, Remove from list, Open selected,
Refresh and a shortcut to folder permissions. Registration rejects protected,
remote/network/device, missing, non-file and unsupported targets. Qt local-file
drop URLs are transport-decoded once; filesystem strings are never repeatedly
decoded. Ordinary text and remote/mixed URL drops are rejected. Literal percent
characters in existing filenames retain their meaning. Each drop/add batch is
bounded to 200 files and the persisted registry to 1,000 unique paths.

Bare and bounded Akiha/please forms of “Open a music file” bind `files.open`
with source `chat.music`. Typed chat and local final voice transcripts use the
same composer route. All registered entries are offered with opaque local IDs;
missing files and files without approved-folder open permission remain visible
and disabled. An empty/unusable catalog gives local Settings guidance without
an unusable raw-path field. Local tooltips disambiguate identical filenames.
For this explicitly requested local registry only, the presentation limit is
1,000 rather than the existing 10-result search limit. Service admission requires
the matching trusted local snapshot, operation and source. Provider/search
candidates retain their existing 5/10 limits; providers cannot select music IDs.

Selection revalidates registration membership, file safety/availability and
current approved-folder open permission under the existing lease lock. It
preserves the request ID, operation and owner epoch. `files.open` still requires
confirmation and the downstream absolute-path and approved-root validation.
Settings Open selected also captures ownership and uses the existing worker
guard; it cannot execute after a newer explicit action or permission revocation.
Registration/removal invalidates old clarification/confirmation state. Save or
permission-repository errors fail locally with fixed messages; registration save
failure rolls back the list and does not log raw exceptions or private paths.

### Exact incremental manifest (16 files)

This manifest describes the music pass on top of the earlier correction work,
not the entire dirty worktree:

1. `project_akiha/config/__init__.py`
2. `project_akiha/config/settings.py`
3. `project_akiha/services/config_store.py`
4. `project_akiha/services/music_file_catalog.py` (new)
5. `project_akiha/ui/music_files_panel.py` (new)
6. `project_akiha/ui/settings_window.py`
7. `project_akiha/app/main.py`
8. `project_akiha/core/actions/clarification.py`
9. `project_akiha/services/action_clarification.py`
10. `project_akiha/app/action_clarification_controller.py`
11. `project_akiha/ui/action_clarification_panel.py`
12. `tests/unit/app/test_music_files.py` (new)
13. `tests/unit/services/test_music_file_catalog.py` (new)
14. `tests/unit/app/test_phase13b_usability.py`
15. `tests/unit/ui/test_settings_window.py`
16. `docs/phases/phase-13-assistant-utilities/PHASE13B.md`

The Settings navigation assertion now expects the ninth page; existing indices
are unchanged. The existing unbound-CLARIFY test now uses “Please open something”
because “Open a music file” is intentionally recognized locally. Its generic
cancel-only/no-lease/no-execution assertions remain intact. Earlier atomic
publication, confirmation, fingerprint, search-continuation, alias, Gemini and
Qt lifecycle implementations are preserved. Package/migration stabilization
files were not edited during this music pass. No new test is disabled or skipped.

### New regressions and connected privacy evidence

There are 14 composed tests in `tests/unit/app/test_music_files.py` and six
catalog/config tests in `tests/unit/services/test_music_file_catalog.py`.
The composed tests reuse fixture setup/teardown only, without inheriting or
importing a discoverable copy of the previous test classes. They cover real
QDragEnterEvent/QDropEvent delivery; CopyAction instead of moving files;
immediate persistence; duplicates; file-picker input; filtering/removal;
25 registered choices through typed and voice composer routes; opaque resolution
and confirmation before execution; empty catalog guidance; unapproved/missing
disabled choices and forged selection; removal/revocation/disappearance;
exact expiry, replay, supersession, provider answers and raw aliases; Settings
worker ownership; remote/mixed/text/oversized drops; save rollback; config reload
and ordinary Settings save; permission-store failure; and connected privacy.
The six service tests cover all audio extensions, passive metadata registration,
invalid/active/missing/remote inputs, protected roots, literal encoded-looking
filenames, Unicode/spaces/percent TOML roundtrip with missing-file retention,
deduplication and the 200/1,000 limits.

Synthetic `MUSIC_PRIVATE_SENTINEL` filenames, path answers and opaque choice IDs
are absent from canonical UI chat, real ChatController/provider messages, every
temporary SQLite table, transcript export, persisted conversation summaries,
actual memory extraction/persistence, delivered notifications, EventBus records,
EventLogger and application logs. Public chat, memory, summary, notification and
production log positive controls run. Only the explicitly intended private user
configuration retains registered references; the local Settings/dropdown UI
displays them deliberately. The external file-open boundary is replaced with a
safe executor in the confirmation test; no user music or OS player was opened.

### Exact commands and final results

Commands ran from the repository root using `.venv313` and `-B`. After the
workspace/environment interruption, the sandbox denied Qt single-instance IPC
and ordinary temporary-file access. Composed/native tests and source smoke were
run with approved local access, preserving the production single-instance guard.
An initial fixture run exposed an executor-key assumption, stale Settings
permission data, and comparing typed choices to strings; these fixtures were
corrected. Importing a test class initially duplicated 16 tests in that selection;
the import was changed to a module reference before final discovery. Final new
selection is exactly 20 tests, and full discovery grew from 1,795 to 1,815.
Initial import-order formatting was corrected before the final gates.

```powershell
.\.venv313\Scripts\python.exe -B -m unittest tests.unit.app.test_music_files tests.unit.services.test_music_file_catalog -q
.\.venv313\Scripts\python.exe -B -m unittest tests.unit.app.test_music_files tests.unit.services.test_music_file_catalog tests.unit.config.test_settings tests.unit.services.test_config_store tests.unit.ui.test_settings_window -q
.\.venv313\Scripts\python.exe -B -m unittest tests.unit.app.test_music_files tests.unit.services.test_music_file_catalog tests.unit.app.test_phase13b_usability tests.unit.app.test_phase13b_composition tests.unit.services.test_phase13b_corrections tests.unit.services.test_action_clarification tests.unit.services.test_phase13b_integration tests.unit.ui.test_phase13b_proposal_flows tests.unit.services.test_provider_action_dispatcher tests.unit.services.test_provider_action_proposal_gateway tests.unit.ui.test_ollama_tool_worker tests.unit.ui.test_hosted_live_session_worker tests.unit.ui.test_assistant_tool_worker -q
.\.venv313\Scripts\python.exe -B -m unittest discover tests -q
for ($musicQtRepeat = 1; $musicQtRepeat -le 10; $musicQtRepeat++) {
  & .\.venv313\Scripts\python.exe -B -m unittest tests.unit.ui.test_behavior_history_window.BehaviorHistoryWindowTest.test_clear_matching_emits_selected_filters_after_confirmation tests.unit.ui.test_hosted_live_session_worker.HostedLiveSessionThreadTest.test_tool_task_failure_stops_visibly_instead_of_stranding_turn -q
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
.\.venv313\Scripts\python.exe -B -m unittest discover -s tests/unit/core/actions -q
.\.venv313\Scripts\python.exe -B -m unittest tests.unit.services.test_assistant_actions tests.unit.services.test_assistant_permissions tests.unit.services.test_assistant_tool_gateway tests.unit.services.test_event_logger tests.unit.database.test_migrator tests.unit.app.test_shutdown tests.unit.app.test_conversation_runtime_router -q
.\.venv313\Scripts\python.exe -B -m ruff check --no-cache project_akiha tests
.\.venv313\Scripts\python.exe -B -m black --check --workers 1 project_akiha tests
.\scripts\smoke_source_app.ps1 -PythonExe (Resolve-Path '.\.venv313\Scripts\python.exe').Path -SmokeRoot (Join-Path $env:TEMP ('akiha-13b-music-' + [guid]::NewGuid().ToString('N'))) -StartupSeconds 8 -ShutdownSeconds 3
git -c safe.directory='C:/Users/MY PC/Desktop/Project Akiha' diff --check
```

The in-memory compilation and static core-boundary command recorded earlier
was rerun unchanged: 547 files compiled, forbidden core imports absent. Git's
repository-ownership check required a command-scoped safe.directory option;
no global Git configuration was changed.

| Gate | Final result |
| --- | --- |
| New music tests | 20 tests in 6.192 seconds; OK; exit 0 |
| Music/config/persistence/Settings | 77 tests in 7.544 seconds; OK; exit 0 |
| Focused Phase 13B including music | 160 tests in 20.487 seconds; OK; exit 0 |
| Required single-process complete discovery | **1,815 tests in 45.489 seconds; OK; no skips; final totals and exit 0** |
| Historical Qt pair | 10/10 runs; two tests each; OK; exit 0 |
| Action boundaries | 65 tests in 0.190 seconds; OK; no skips; exit 0 |
| Security/permissions/database/log/shutdown/runtime | 88 tests in 2.210 seconds; OK; exit 0 |
| Ruff | All checks passed; exit 0 |
| Black | 547 files unchanged; exit 0 |
| In-memory compilation/static boundaries | 547 files; PASS; exit 0 |
| Source/database/log smoke | 15 required tables and production log checks passed; harness exit 0 |
| git diff --check | Exit 0; existing LF/CRLF warnings only |

The three symlink cases skipped in the earlier environment ran successfully
under this environment's approved local access. Their skip conditions and
assertions were not changed. No garbage collection was disabled and full-suite
discovery was not split into subprocesses.

### Remaining manual checks and scope

The actual Settings widget was rendered at 1,120 x 760 with synthetic files to
check page geometry. Offscreen font glyph rendering was unavailable, so this
does not establish native desktop typography or manual owner acceptance.
Remaining owner checks: restart the source app; drag actual local music into
Settings > Music files; reload/restart and verify persistence; issue the command
by typing and microphone; select, confirm and open the intended file; remove a
registration without deleting the original; exercise missing files, permission
revocation, timeout, supersession and Gemini suspension/explicit restart.

Source smoke PID 21636 reported `CloseMainWindowRequested=False`,
`ForcedStop=True`, child exit `-1`, `StateDirExists=False`. Startup/database/log
checks passed, but **graceful shutdown remains unproved**, including shutdown
with a pending lease. No clean packaged build was run; packaged smoke remains
pending until the separately identified destructive WorkDir cleanup guard is
fixed. HEAD remains `ea93f727aac5ee10331619c897bf919c4323aba2` and the index is
empty. No commit, push, packaging, phase completion, owner acceptance or Phase
13C activation occurred. Another independent audit and owner acceptance remain
required.

## Handpicked files and album-folder drops — 2026-10-07

**Acceptance remains pending. This revision has not passed the required composed
or full single-process gates in the current restricted environment.** The owner
explicitly requested automatic permission for the containing folder of handpicked
music, then requested dropping an entire album folder. This supersedes the prior
music pass's requirement to approve each new music folder manually.

### Behavior and permission scope

Dropping a valid music file, or selecting it with Add files, registers its existing
location and grants only `files.open` for its containing folder. Dropping an album
folder, or using the new Add folder button, recursively registers supported audio
and grants only `files.open` for the selected album folder. Existing search grants
are preserved; no new `files.search`, application or Spotify permission is granted.
The existing root-containment policy includes descendants, so approval covers
other supported files and subfolders in that root, not just the registered songs.
Settings now discloses this scope and the continued file-opening confirmation.

Files are left in place. ZIP/archive files are not extracted or registered as
music; extract an album before dropping its folder. Folder scans have shared
limits of 200 accepted songs per selection, 4,000 inspected entries and eight
subfolder levels. File/folder input batches remain limited to 200 and the whole
registry to 1,000. A limited scan reports that remaining files/subfolders must
be added separately. Sorted bounded entries provide stable selection order
within the inspected subset. Links/reparse paths, protected paths, unsupported
files and unsafe roots still fail closed through existing path/audio policies.
Empty/non-audio/rejected folders do not request permission.

The pure catalog returns private `approval_roots` metadata for accepted local
selections. A separate typed Settings registration signal carries the selected
file/folder inputs to the production callback, which recomputes the catalog
result and verifies that it matches the displayed registry before saving.
A configuration-only change can remove references but cannot add music or grant
permission. Registration is saved before granting roots; a failed config save
does not grant permission. After a successful save, each root uses the existing
validated/idempotent permission API. Per-root grant failures retain the registered
references and show fixed local guidance; unavailable grants cannot enable a
choice. Raw storage exceptions and paths are not logged.

New registration invalidates old leases/confirmations before grants. Removal,
refresh, config reload and application startup do not grant or restore permission.
An explicit new drop/picker selection may re-approve a revoked folder, including
already-registered songs. Removing a reference leaves files and the deliberately
granted folder permission in place; the Remove button's tooltip directs the user
to revoke it in Actions. Opaque selection, absolute-path/root validation, expiry,
replay protection, ownership guards and file-opening confirmation remain intact.
No provider can invoke this Settings-only registration control.

### Exact incremental manifest (seven files)

1. `project_akiha/services/music_file_catalog.py`
2. `project_akiha/ui/music_files_panel.py`
3. `project_akiha/ui/settings_window.py`
4. `project_akiha/app/main.py`
5. `tests/unit/services/test_music_file_catalog.py`
6. `tests/unit/app/test_music_files.py`
7. `docs/phases/phase-13-assistant-utilities/PHASE13B.md`

A pre-pass SHA-256 snapshot covered 639 source/test/document/script files. The
other 632 files are unchanged, including the separately documented stabilization,
provider alias, ownership, Gemini, Qt lifecycle, package and migration work.

### Regressions and evidence

Added five catalog tests: nested audio with only the selected root; empty/non-audio
folders; song/entry/depth scan bounds; no-follow link entries; protected subfolders.
Added seven composed tests: exact parent-folder open-only grant after a real file
drop; nested album drop with one persisted root; folder picker/duplicate drop
preserving search grants; reload/refresh/removal without implicit re-approval;
unsupported/protected selections without grants; partial SQLite grant failure
with private exception suppression; configuration-only updates without selection.

Existing unsupported-input coverage was updated because directories are now valid
local selections. Existing unavailable-choice coverage explicitly revokes newly
granted scopes before testing disabled/rejected selection. Save-failure coverage
now asserts no grant call. The connected privacy test now registers a synthetic
album: its root sentinel is allowed only in `assistant_action_permissions` and
the intended private user config, while song/answer/ID/root sentinels must remain
absent from transcript, provider, conversation SQLite, export, real persisted
memory/summary, notifications, EventBus/EventLogger and application logs. These
composed assertions remain enabled and discovered, but their execution is blocked
by startup IPC in this environment; they are not reported as passing.

An independent supporting probe executed the actual production callback extracted
from `main.py` and connected it to a real SettingsWindow and Qt drag/drop events,
using the real catalog, UserConfigStore, clarification service, permission service
and temporary SQLite repository. Only the unrelated alias-refresh callback was
replaced in that isolated probe. It passed nested registration, ready UI entries,
persisted exact root/open permission, preserving an existing search grant,
revocation without reload re-approval, explicit redrop, and reference removal
without source deletion. This is callback evidence, not a complete application
composition, provider/privacy proof or replacement for the required full gate.

### Validation commands, results and environment limitation

Temporary fixtures were redirected into unique ignored `dist/music-*` directories
because the sandbox's default `AC/Temp` allowed creation but denied subsequent
canonical-path access. Local Python-runtime, native temporary-directory and
network/IPC permissions were requested and granted. Nevertheless this standalone
probe still fails before any application graph is constructed:

```python
server = QLocalServer()
server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
server.listen("akiha-test-" + uuid4().hex)
# False: QLocalServerPrivate::addListener: Access is denied.
```

Default-option IPC can be created, but production requires user-scoped IPC. The
production guard/options were not changed or mocked to manufacture a passing
gate. Faulthandler showed composed startup waiting in `main.py`'s
`QMessageBox.critical` error branch after `SingleInstanceCoordinator.start()`.
The stalled owned test processes were interrupted; no unrelated app was stopped.

Commands were run with `.venv313`, `-B` and TEMP/TMP pointed to a fresh writable
workspace directory for test selections:

```powershell
.\.venv313\Scripts\python.exe -B -m unittest tests.unit.services.test_music_file_catalog -q
.\.venv313\Scripts\python.exe -B -m unittest tests.unit.services.test_music_file_catalog tests.unit.config.test_settings tests.unit.services.test_config_store tests.unit.ui.test_settings_window -q
.\.venv313\Scripts\python.exe -B -m unittest tests.unit.services.test_phase13b_corrections tests.unit.services.test_action_clarification tests.unit.services.test_phase13b_integration tests.unit.ui.test_phase13b_proposal_flows tests.unit.services.test_provider_action_dispatcher tests.unit.services.test_provider_action_proposal_gateway tests.unit.ui.test_ollama_tool_worker tests.unit.ui.test_hosted_live_session_worker tests.unit.ui.test_assistant_tool_worker -q
.\.venv313\Scripts\python.exe -B -m unittest tests.unit.app.test_music_files tests.unit.services.test_music_file_catalog -q
.\.venv313\Scripts\python.exe -B -m unittest discover tests -q
for ($musicFolderQtRepeat = 1; $musicFolderQtRepeat -le 10; $musicFolderQtRepeat++) {
  & .\.venv313\Scripts\python.exe -B -m unittest tests.unit.ui.test_behavior_history_window.BehaviorHistoryWindowTest.test_clear_matching_emits_selected_filters_after_confirmation tests.unit.ui.test_hosted_live_session_worker.HostedLiveSessionThreadTest.test_tool_task_failure_stops_visibly_instead_of_stranding_turn -q
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
.\.venv313\Scripts\python.exe -B -m unittest discover -s tests/unit/core/actions -q
.\.venv313\Scripts\python.exe -B -m unittest tests.unit.services.test_assistant_actions tests.unit.services.test_assistant_permissions tests.unit.services.test_assistant_tool_gateway tests.unit.services.test_event_logger tests.unit.database.test_migrator tests.unit.app.test_shutdown tests.unit.app.test_conversation_runtime_router -q
.\.venv313\Scripts\python.exe -B -m ruff check --no-cache project_akiha tests
.\.venv313\Scripts\python.exe -B -m black --check --workers 1 project_akiha tests
git -c safe.directory='C:/Users/MY PC/Desktop/Project Akiha' diff --check
```

| Gate | Current result |
| --- | --- |
| Catalog | 11 tests, 0.215 seconds, OK, exit 0 |
| Catalog/config/store/Settings | 68 tests, 1.721 seconds, OK, exit 0 |
| Available Phase 13B correction/service/worker selection | 108 tests, 0.884 seconds, OK, exit 0; excludes blocked composition/usability tests |
| Independent production-callback/drop probe | PASS, exit 0; supporting evidence only |
| Composed music selection | BLOCKED at production user-scoped IPC startup; interrupted, exit 1, no totals |
| Required full single-process discovery | BLOCKED at startup IPC; interrupted, exit 1, **no final unittest totals**; not a passing gate |
| Historical Qt pair | 10/10 runs, two tests each, OK, exit 0 |
| Action boundaries | 65 tests, 0.370 seconds, OK (three existing symlink skips), exit 0 |
| Security/database/log/shutdown/runtime | 88 tests, 2.033 seconds, OK, exit 0 |
| Ruff / Black | PASS; 547 files unchanged; exit 0 |
| In-memory compilation/static core boundaries | 547 files, PASS, exit 0 |
| Discovery inventory | 1,827 discovered; count only, not a passing full run |
| Source/database/log smoke | No fresh source-smoke pass: same production IPC limitation prevents startup |
| git diff --check | Exit 0; existing LF/CRLF warnings only |

There are now 32 music tests (21 composed, 11 catalog), with 12 added in this pass.
No test or garbage collection was disabled and no required gate was split into
subprocesses. Earlier passing 1,815-test totals apply to the preceding revision,
not this changed revision. Fresh composed music/privacy, the 172-test focused
selection and complete 1,827-test discovery must be rerun in a normal local
environment with functioning user-scoped IPC. Graceful shutdown remains unproved.

### Remaining owner checks and phase status

Restart the source app, drop a file and an extracted album folder, verify ready
entries and the exact folder approval in Actions, then choose/confirm the desired
song through typed and microphone requests. Verify removal, duplicate drops,
revocation, deliberate re-approval, expiry/supersession, partial scan notices and
Gemini suspension/explicit restart. Rerun source/database/log smoke and graceful
shutdown with a pending lease. No packaged build was run; the separately identified
WorkDir cleanup guard remains a prerequisite. No commit, push, phase completion,
owner acceptance or Phase 13C activation occurred. HEAD/index remain unchanged.

## Spotify generic-music recognition follow-up — 2026-10-07

While the album-folder correction was being validated, the owner reproduced
“Play Music on Spotify” entering ordinary chat and receiving an incorrect
capability denial from the conversational provider. Before editing, independent
calls to the production parser and incomplete-command recognizer both returned
`None` for that exact phrase. The specific command “Play track Blinding Lights
by The Weeknd on Spotify” returned `spotify.play_track` with service `spotify`,
track query `Blinding Lights`, and artist query `The Weeknd`.

The exact pre-fix branch was composer -> `route_answer` (no answer) ->
`incomplete_command` (None) -> deterministic bridge parse (None) -> ordinary
chat/provider routing. This demonstrates a local recognition gap, not evidence
that the Spotify integration is unavailable. Live authentication, permission,
device availability and playback were not tested and are not claimed to work.

Added three bounded exact incomplete forms: “play music on Spotify”, “play a song
on Spotify” and “play a track on Spotify”, using the existing single Akiha/please
prefix handling and negation envelope. These bind the existing `spotify.play_track`
operation with only service `spotify`, leaving the required `track_query` absent.
The central lease publishes a local question: “Which song would you like to play
on Spotify? Enter its title.” No track, queue or content is chosen implicitly.
The local answer revises the same owned request and dispatches through existing
permission, authentication/device and bounded catalog matching. Specific track,
artist, album, playlist and explicit playback/resume commands retain their prior
routes. Arbitrary prose, negation, compounds and repeated name prefixes do not
create a new incomplete action, and an unbound provider CLARIFY topic remains
generic. Questions/answers stay in the local clarification surface.

### Incremental manifest and regressions

This follow-up changes six files (the phase record overlaps the seven-file album
manifest above):

1. `project_akiha/app/action_clarification_controller.py`
2. `project_akiha/ui/action_clarification_panel.py`
3. `tests/unit/services/test_action_clarification.py`
4. `tests/unit/ui/test_phase13b_proposal_flows.py`
5. `tests/unit/app/test_phase13b_usability.py`
6. `docs/phases/phase-13-assistant-utilities/PHASE13B.md`

Six new tests cover exact/prefixed vague forms without invented targets;
operation/owner/request preservation and replay rejection after a local song
answer; negation/prose/compound exclusions and preservation of specific title/
artist parsing; real clarification-panel question and submission with no earlier
execution; composed typed/voice routes excluding provider/transcript/SQLite/
export with a synthetic target; and the composed deterministic specific-track
route. The two new composed tests remain enabled/discovered but share the current
user-scoped Qt IPC startup blocker. They are not reported as passing.

### Exact additional validation and limits

Using a fresh workspace TEMP/TMP directory as above:

```powershell
.\.venv313\Scripts\python.exe -B -m unittest tests.unit.services.test_action_clarification tests.unit.ui.test_phase13b_proposal_flows tests.unit.services.test_assistant_action_bridge -q
.\.venv313\Scripts\python.exe -B -m unittest tests.unit.services.test_music_file_catalog tests.unit.services.test_phase13b_corrections tests.unit.services.test_action_clarification tests.unit.services.test_phase13b_integration tests.unit.ui.test_phase13b_proposal_flows tests.unit.services.test_provider_action_dispatcher tests.unit.services.test_provider_action_proposal_gateway tests.unit.ui.test_ollama_tool_worker tests.unit.ui.test_hosted_live_session_worker tests.unit.ui.test_assistant_tool_worker -q
.\.venv313\Scripts\python.exe -B -m ruff check --no-cache project_akiha tests
.\.venv313\Scripts\python.exe -B -m black --check --workers 1 project_akiha tests
git -c safe.directory='C:/Users/MY PC/Desktop/Project Akiha' diff --check
```

| Additional gate | Result |
| --- | --- |
| Spotify parsing, clarification and real panel | 90 tests, 0.079 seconds, OK, exit 0 |
| Available music/Phase 13B service/worker selection | 123 tests, 1.076 seconds, OK, exit 0 |
| Ruff/Black | PASS, 547 files unchanged, exit 0 |
| In-memory compilation/static boundaries | 547 files, PASS, exit 0 |
| Discovery inventory | 1,833 discovered, count only; six more than the album-folder revision |

An initial synthetic correlation ID contained spaces and was corrected to an
allowed opaque identifier; an initial overlong question string was reformatted.
No existing assertions or skip conditions were weakened. Final combined changes
are 12 files against the 639-file pre-turn snapshot; the other 627 remain identical.
The required 178-test focused composition selection and 1,833-test single-process
complete gate still require a normal environment with working user-scoped IPC;
earlier passing totals do not certify this revision. The source smoke and graceful
shutdown limits recorded above remain. No commit, push, packaging, phase completion,
owner acceptance or Phase 13C activation occurred.


## Local Spotify listening-history picker — 2026-10-07

Status: implementation and available checks completed; full application gates and
owner acceptance remain pending. This is a bounded UX change to the existing
Spotify play operation, not Phase 13C activation.

### Source trace and final owner-requested behavior

The previous track dropdown came from search, not listening history. The actual
route is `SpotifyTrackPlaybackExecutor.execute` -> `_search_track_candidates` ->
`SpotifyClient.search`, initially with `track:<title> artist:<artist>` (artist part
optional), then the existing relaxed query when needed. Candidates are validated,
bounded to five and may be ranked by the local preference ranker. An unresolved
play returns `metadata['track_candidates']`; `handle_action_dispatch` delegates to
`ActionClarificationController.handle_local_result`, which atomically publishes
those search candidates into the local clarification panel. The owner supplied
no exact preceding answer or three labels, so the query of that particular live
attempt is not independently identified. There is no recently-played/fallback
list wired to that old picker.

The final owner follow-up requests deduplication. A recognized local Spotify play
request with no target now opens two deliberately separate modes:

- **Recently played:** request exactly
  `GET /v1/me/player/recently-played?limit=20`; display up to **10 distinct tracks**
  from those latest 20 plays, retaining the API's newest-first order. Repeated
  Spotify track URIs appear once, keeping their newest occurrence. Different
  track IDs/versions (including instrumentals) remain distinct. If the latest
  20 plays contain fewer than 10 distinct tracks, the picker contains fewer;
  it does not fetch older pages or fill with search results.
- **Search by song and artist:** locally enter the title and optional artist,
  preserving the original play operation and its existing search route.

The separate history-picker maximum is 10. The previous Spotify **search** cap
remains five. Specific track, artist, album and playlist commands retain their
existing deterministic/search routes. No song plays on presentation or fetching.
No provider or unbound CLARIFY topic can choose history, switch modes or select an
opaque local history choice.

The existing OAuth scope request already includes `user-read-recently-played`;
that scope list was not changed. `SpotifySession.has_scope` checks the *granted*
access-token scopes before fetching. Missing scope produces a local reconnect
explanation without opening authorization, requesting new scopes or searching.
Empty history, disconnected accounts, 403/401/429/API/transport failures have
fixed privacy-safe local messages. Unavailable tracks remain visible but disabled.
The endpoint reference is
https://developer.spotify.com/documentation/web-api/reference/get-recently-played.

### Ownership, lifecycle and privacy design

A history fetch captures an immutable `SpotifyHistoryIdentity`: complete original
lease identity (owner epoch, digest, revision, nonce, creation/deadline), original
request/action/source/parameters, unique fetch nonce and account generation.
`start_spotify_history` captures under the central lease lock. The single atomic
`publish_spotify_history` operation verifies that exact captured identity and
request, checks the account/permission guard, rechecks after reentrant callbacks
and expiry, and publishes a trusted local snapshot without claiming new ownership
or extending the 120-second deadline. Duplicate, stale, changed-fingerprint,
expired, cancelled, revoked and superseded deliveries fail closed.

History entries receive random opaque request-bound choice IDs, with direct
validated Spotify track URIs resolved locally. Selection requires LOCAL_UI,
enabled entry, exact identity and current account/playback permission. Search-mode
switching discards the snapshot/fetch identity and increments revision while
preserving owner and deadline; a late history result cannot replace its fields.
Account reconnect/disconnect/client changes advance a memory-only generation.
Settings session-change delivery also invalidates clarification/confirmation.
Account authority survives selection through an execution guard and the owned
worker cancellation token at existing executor cancellation checkpoints. Existing
permission, confirmation, validation and playback/device checks remain mandatory.

The fetch runs on `SpotifyHistoryThread`, participates in the existing active-tool
cancellation/shutdown list, emits no raw exception or listing, and starts no
playback. Standalone Qt tests join it and verify widget destruction on the GUI
thread. This does not prove full application graceful shutdown.

The list is transient private picker data: no ChatController, provider, transcript,
export, memory, summary, notification or EventBus/EventLogger publication occurs
when fetching or presenting it. Pending snapshots/choice IDs disappear on terminal
resolution, expiry/cancellation, mode switch or supersession. Only digests/account
checks survive selection; selected history result summaries/metadata are reduced
to fixed status text before ordinary presentation, so titles/URIs are not copied
out of the picker. Existing action audits still record the required operational
status with normalized target `spotify`, without a track listing. No schema,
provider catalog, OAuth scope list or configured permission was expanded.

### Exact incremental manifest

These 15 files changed against the pre-pass snapshot (five are new). The other 609
pre-existing snapshot files, including music-folder registration, package/migration
and Phases 1–12 stabilization work, remain intact.

1. `project_akiha/app/main.py`
2. `project_akiha/core/actions/clarification.py`
3. `project_akiha/services/action_clarification.py`
4. `project_akiha/integrations/spotify/client.py`
5. `project_akiha/integrations/spotify/session.py`
6. `project_akiha/integrations/spotify/history.py` (new)
7. `project_akiha/ui/action_clarification_panel.py`
8. `project_akiha/ui/assistant_action_worker.py`
9. `project_akiha/ui/spotify_history_worker.py` (new)
10. `tests/unit/app/test_phase13b_usability.py`
11. `tests/unit/ui/test_phase13b_proposal_flows.py`
12. `tests/unit/integrations/spotify/test_history.py` (new)
13. `tests/unit/ui/test_spotify_history_picker.py` (new)
14. `tests/unit/app/test_spotify_history.py` (new)
15. `docs/phases/phase-13-assistant-utilities/PHASE13B.md`

The two prior generic-Spotify UI tests now deliberately switch from the new
history default to Search before answering; their ownership, privacy, dispatch
and replay assertions remain. No new test is disabled or marked skipped and the
45 new history tests have distinct discovery IDs.

### Regressions and connected verification

- 27 token/client/lease tests: actual fixed history URL and limit; newest order;
  URI deduplication and different versions; all-repeat histories; no older-page
  fallback; absent scope without expanded authorization; empty history;
  unavailable tracks; missing artists without invalid empty parameters; fixed
  401/403/429/other error handling; disconnect during response; account switch;
  private repr/evidence; immutable ownership/deadline; opaque one-use selection;
  separate five/ten caps; supersession/cancellation/revocation/exact expiry;
  fingerprint change/replay; provider/forged selection rejection; mode-switch
  late results; reentrant new-owner/expiry guards; specific-query routing;
  post-selection account invalidation of executor token; local-only artist input.
- 12 Qt/callback tests: four standalone tests pass for actual widgets, history
  selection, title/artist submission, real joined fetch thread and cancellation
  barrier. Eight further tests use the *actual unmodified main callbacks*
  extracted into a bounded composition with real panel, token/client and temporary
  SQLite permissions. They cover endpoint/picker wiring, disabled tracks, scope,
  empty history, barrier-controlled revocation/supersession/mode change and SQLite
  exclusion. These eight are blocked by the Windows asyncio socket-pair issue
  described below; they are not claimed as passing or as full-app composition.
- Six complete application tests: actual typed composer/local voice history
  routing; specific track/artist/album/playlist routes; search fields and ownership;
  account invalidation; error surfaces without fallback; connected privacy.
  The privacy test builds the real app, uses real ChatController/provider-message
  construction/export/memory/summary/notification/EventBus/logging/SQLite paths,
  makes positive public memory/summary/notification assertions, and selects a
  history entry through real validation, permissions, bridge and SQLite action
  audit (only external playback is replaced). It rejects title/artist/choice-ID
  sentinels across every connected surface and checks the audit target is
  `spotify`. These six remain enabled/discovered but blocked at app startup.

### Exact commands and final results

Validation used an isolated workspace TEMP/TMP directory; no real account was
queried, playback started, source music changed or application packaged.

```powershell
$historyTestTemp = Join-Path $PWD 'dist\spotify-history-validation'
New-Item -ItemType Directory -Path $historyTestTemp -Force | Out-Null
$env:TEMP=$historyTestTemp
$env:TMP=$historyTestTemp

.venv313\Scripts\python.exe -B -m unittest tests.unit.integrations.spotify.test_history tests.unit.ui.test_spotify_history_picker.SpotifyStandalonePickerTest tests.unit.services.test_action_clarification tests.unit.services.test_music_file_catalog tests.unit.services.test_phase13b_corrections.CorrectionOwnershipTest.test_barrier_new_action_wins_between_owner_check_and_publication tests.unit.services.test_phase13b_corrections.CorrectionOwnershipTest.test_atomic_publication_requires_exact_request_identity tests.unit.services.test_phase13b_corrections.CorrectionProviderPathTest -q
.venv313\Scripts\python.exe -B -m unittest tests.unit.integrations.spotify.test_client tests.unit.integrations.spotify.test_session tests.unit.integrations.spotify.test_auth tests.unit.core.actions.test_models_registry tests.unit.core.actions.test_validation tests.unit.core.actions.test_path_policy tests.unit.core.actions.test_permissions tests.unit.app.test_shutdown -q
.venv313\Scripts\python.exe -B -m unittest tests.unit.app.test_phase13b_composition tests.unit.app.test_phase13b_usability tests.unit.app.test_music_files tests.unit.services.test_action_clarification tests.unit.services.test_phase13b_corrections tests.unit.services.test_phase13b_integration tests.unit.ui.test_phase13b_proposal_flows tests.unit.services.test_provider_action_dispatcher tests.unit.services.test_provider_action_proposal_gateway tests.unit.ui.test_ollama_tool_worker tests.unit.ui.test_hosted_live_session_worker tests.unit.ui.test_assistant_tool_worker tests.unit.services.test_music_file_catalog tests.unit.integrations.spotify.test_history tests.unit.ui.test_spotify_history_picker tests.unit.app.test_spotify_history -v
.venv313\Scripts\python.exe -B -m unittest discover -s tests -t . -v
.venv313\Scripts\python.exe -B -m ruff check --no-cache project_akiha tests
.venv313\Scripts\python.exe -B -m black --check project_akiha/app/main.py
.venv313\Scripts\python.exe -B -m black --check project_akiha/services/action_clarification.py
.venv313\Scripts\python.exe -B -m black --check project_akiha/ui/action_clarification_panel.py
.venv313\Scripts\python.exe -B dist\spotify-history-static-check.py
git -c safe.directory='C:/Users/MY PC/Desktop/Project Akiha' diff --check
```

| Gate | Result |
| --- | --- |
| Available focused regression selection | **78 tests**, 0.273s, OK, exit 0; includes 31 passing new tests |
| Spotify/action/path/permission/shutdown selection | **81 tests**, 0.193s, OK with **one existing skip**, exit 0 |
| Full Phase 13B focused selection | Blocked on its first composed startup in user-scoped Qt IPC; interrupted, exit **-1073741510**, no final totals, **not PASS** |
| Required single-process discovery | Stalled in `ChatControllerTest.test_abandoned_stream_never_persists_or_processes_partial_assistant` during Windows asyncio loop/socket-pair creation; interrupted, exit **-1073741510**, no final totals, **not PASS** |
| Discovery inventory | **1,878 unique discovered tests**, including **45 new**; count only, not a full-suite pass |
| Ruff | All checks passed, exit 0 |
| Black CLI for main/service/panel | All unchanged, exit 0 for each |
| Whole-source Black API check | **552 files unchanged**, project mode line length 88/PY312, exit 0 |
| In-memory compilation / core static imports | **552 files**, PASS, exit 0 |
| New-test static quality / unique IDs | No skip/GC-disable directives, no duplicate IDs, exit 0 |
| git diff --check | Exit 0; existing LF/CRLF notices only |

The whole-source Black CLI with multiple paths/`--workers 1` stalled in this
restricted environment and was interrupted (exit 1). The independently completed
whole-source check uses `black.decode_bytes(..., mode)` plus
`black.format_file_contents(..., fast=False, mode=Mode(line_length=88,
target_versions={TargetVersion.PY312}))` in one process, preserving BOM handling
without multiprocessing. The ignored `dist/spotify-history-static-check.py`
contains that read-only check, in-memory compilation, core import boundaries,
discovery inventory and unique/new-test checks. Initial validation also found a
mistyped existing registry-test module name (corrected to `test_models_registry`)
and a same-ID pending-lease cap-test setup error (corrected to test a fresh lease,
not weaken the cap). Final results above supersede those attempts.

The historical Qt pair was attempted twice in its original order using
`unittest.defaultTestLoader.loadTestsFromNames` and `TextTestRunner(verbosity=2)`:

```text
BehaviorHistoryWindowTest.test_clear_matching_emits_selected_filters_after_confirmation
HostedLiveSessionThreadTest.test_tool_task_failure_stops_visibly_instead_of_stranding_turn
```

Both attempts completed **2 tests, FAILED (failures=2), exit 1**: the behavior
history test passed; the hosted test's readiness and worker-join assertions failed.
A `faulthandler.dump_traceback_later(2)` diagnostic proves that worker is blocked
inside `socket.accept` -> `_fallback_socketpair` -> Windows
`ProactorEventLoop._make_self_pipe` -> `asyncio.run`, before the hosted runtime
starts. No memory-write Qt abort was observed in these attempts. This is distinct
from the previously corrected Qt lifecycle defect. It is an environment blocker,
not a passing ten-repeat Qt gate; repeating ten times was not claimed. The same
stack explains the bounded SQLite callback harness stall. No socket/network/Qt
policy, test skip, garbage collection or crash dialog was modified to hide it.
The independent `QLocalServer(UserAccessOption)` probe also returned false with
`QLocalServerPrivate::addListener: Access is denied.`

Source/database/log smoke used:

```powershell
$historySmokeRoot = Join-Path $PWD ('dist\spotify-history-source-smoke-' + [guid]::NewGuid().ToString('N'))
& .\scripts\smoke_source_app.ps1 -SmokeRoot $historySmokeRoot -PythonExe (Join-Path $PWD '.venv313\Scripts\python.exe') -StartupSeconds 2 -ShutdownSeconds 1
```

It exited **1** because the expected isolated `Akiha` data directory was not
created; source startup was blocked before database/log initialization. The
script disposed its own process. **No source/database/log smoke pass or graceful
shutdown proof is claimed.** Actual account scope, history contents and playback
are still manual checks, not inferred from synthetic transports.

### Remaining owner checks and acceptance status

Restart the source app; connect Spotify with its existing history scope and
playback permission; say/type “Play music on Spotify”; inspect newest-first,
deduplicated history, unavailable entries, empty/failure guidance and deliberate
selection. Switch to Search and verify title plus artist, and specific track/
artist/album/playlist requests. Exercise account reconnect/switch/disconnect,
revocation, timeout, supersession/replay and Gemini suspension/explicit restart.
Rerun the enabled 14 blocked new tests, complete focused selection, required
single-process complete discovery, historical pair repetitions and fresh source/
database/log smoke in a normal environment with working local IPC. Preserve the
separately recorded packaged-build WorkDir-cleanup prerequisite. Graceful shutdown
with a pending lease remains **unproved**.

No commit, push, package, phase completion, owner acceptance or Phase 13C
activation occurred. HEAD remains `ea93f727aac5ee10331619c897bf919c4323aba2`
and the index is unchanged. Phase 13B continues awaiting independent audit and
owner acceptance; this record does not waive any required gate.
