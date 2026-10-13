# Phase 13D–13I implementation and consolidated verification

Recorded 2026-10-09. Final owner acceptance is pending. No commit or push was
made by this continuous task. No recurrence, calendar synchronization, restore,
import, arbitrary browsing, file ingestion/mutation, external-account write,
installer, signing or update functionality was added.

## Required context and dependency order

There are no separate PHASE13D–PHASE13I documents in this checkout. The complete
Phase 13 README, 13A contracts, accepted 13B record, complete 13C record, Phase 8
action boundaries, Phase 12 delivery/runtime architecture, privacy/security and
codebase records are the maintained scope. The owner authorized all remaining
subphases continuously; 13E–13H were retained.

The owner's corrected normal Windows evidence at
`dist/phase13c-verification-20261009-030430-a61707` was reconciled before 13D:
1924 unique discovered and executed tests, no skips, exit 0; 38 timer tests;
all seven cleanup tests including real junction creation; ten Qt pairs;
source quality, boundaries and database/log smoke. Captured implementation
hashes matched. Owner timer-behavior acceptance remains recorded.

## Implemented behavior and boundaries

- **13D:** explicit one-shot local date/time and IANA timezone; missing fields
  and DST ambiguity/nonexistence ask locally. Create/list/cancel/snooze reuse
  the typed registry, local-request permissions, leases and the existing single
  schedule owner. UTC reminder deadlines share its timer tick; no second
  scheduler. Migration 0016 extends 0015 through the existing migrator, preserves
  inbox rows/issued-ID high water and adds minimal reminder metadata and snooze
  request tombstones. Concurrent expiry and sanitized inbox receipt insertion
  form one transaction. At most 100 pending reminders, within 366 days; exactly
  one hour overdue remains deliverable, older missed reminders enter the inbox
  silently. Cancellation and replay cannot create duplicate receipts.
- **13E:** provider-neutral transient weather snapshot, fixed-host HTTPS GET
  adapter, six-second per-request timeout, 512 KiB response bound, redirects
  denied. Coordinates require explicit Settings configuration and enablement.
  Current conditions and three-day forecast show source, UTC time, age/staleness
  and model uncertainty. Optional official NWS headlines are bounded to three
  and explicitly limited in coverage; unsupported locations/failures never
  imply an all-clear. No arbitrary URL/action authority or weather memory.
  Network results appear only in the local Utilities panel; action/audit results
  are generic. Cancellation or changed location configuration discards results.
  The endpoint contracts were checked against [Open-Meteo documentation](https://open-meteo.com/en/docs)
  and [official NWS documentation](https://www.weather.gov/documentation/services-web-api).
- **13F:** reuses existing contextual directory navigation, expiring local
  context, approved-root discovery, permission rechecks, immutable search
  continuation and bounded ambiguity picker. No competing navigation framework
  or file-content reader was added. New composed probes verify current-root
  binding, multiple matches, supersession, revocation and downstream rejection
  of injected outside-root paths. Existing traversal/reparse/security tests
  remain enabled and pass.
- **13G:** trusted-local selection of 1–100 conversations or active memories;
  new absolute local JSON destination; confirmation every time. Version 1
  manifest records selection/count and SHA-256 of the canonical records array.
  Only explicitly selected whitelisted fields are read in a consistent SQLite
  snapshot. Credentials/configuration, raw provider/system records, embeddings,
  notification receipts, schedules, logs and voice references are excluded.
  Opaque draft IDs bind exact request/fingerprint and ownership, expire in
  60 seconds, and consume once. Writing is bounded to 10 MiB; final publication
  occurs under the existing ownership lock using an atomic no-overwrite hard
  link. Changed ownership, expiry, cancellation, removed data, unsafe paths and
  unwritable/unsupported filesystems fail safely. Existing files remain intact.
- **13H:** focused Utilities Settings page for schedule controls, explicit
  location/opt-in weather, health, completed-label retention and selected export.
  Existing health registry/inbox/channel arbitration remain the surfaces.
  Bounded poll-delay, missed-recovery and presentation-failure diagnostics
  contain no purpose labels, coordinates, export destinations or provider data.
  Completed labels redact after 1–365 configured days, default 30; minimal
  identity/receipts remain for replay protection. Settings control styling was
  corrected after the existing theme test reproduced missing object names.
- **13I:** complete single-process discovery, static/source checks, historical
  Qt repetitions and independent production-service probes passed. Cleanup
  safety was verified before the new clean candidate build. Owner checklist
  remains pending; package results are recorded below when actually obtained.

`tzdata==2026.3` is pinned (already present in the verified environment), collected
by both builders and required by the package validator together with migration
0016. No installation or unrelated service restart was performed.

## Review and correction evidence

Bounded source review inspected registry, validation, permissions, readiness,
composer/result routing, lease ownership, schedule/repository transactions,
weather transport, export publication, Qt wiring and build guards. Independent
probes were written separately from the regressions and used production
services: eight simultaneous receipt claims yielded one receipt, restart did
not redeliver, private purpose did not enter inbox/export, selected export
integrity matched, system/unselected data stayed excluded, and supersession
prevented writing and removed temporary output. DST ambiguity/nonexistence
failed closed. This is agent-run review/probing, not a separate human review
or owner acceptance.

The first consolidated run reached 1987 totals and failed four historical tests
that asserted reminders/weather/exports remained contract-only. Updated exact
registry and contract assertions preserve all explicit exclusions. The natural
wrapper test now verifies an unsupported reminder cannot become an app launch:
it binds reminder intent with invalid time and fails readiness locally. No
tests were removed, disabled, skipped or weakened. The final complete run has
1990 unique test IDs, every ID present in output, zero skips. The new selection
contains 64 tests and passes independently. Initial navigation probe assumptions
were corrected to check hashed roots and actual downstream permission denial,
rather than assuming allocation of a worker itself executes an action.

Connected tests use the actual composer, ChatController, temporary real SQLite,
provider-message builder, export, memory extraction/persistence, summary closure,
notification records and production events/logs. Synthetic sentinels remain
absent from those connected surfaces. No real microphone/cloud account or
reference-audio synthesis is inferred from mocked transport tests.

## Exact automated source evidence

Evidence: `dist/phase13-consolidated-verification-final-20261009`.
Invocation:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify_phase13c.ps1 -OutputDir dist/phase13-consolidated-verification-final-20261009
```

This existing verification script runs the supported selections below; its
historical filename does not limit full discovery to timers.

| Gate | Command/result | Exit |
| --- | --- | --- |
| Inventory/static | `python -B inventory_static.py`: 1990 unique IDs; 576 files compiled; core import boundaries pass | 0 |
| Cleanup guard | `python -B -m unittest tests.unit.services.test_build_cleanup_guard -v`: 7, 1.332s, real junction assertions pass | 0 |
| Timers | documented service + composed timer selection: 38, 3.970s | 0 |
| Focused | exact selection in `verify_phase13c.ps1`: 141, 2.143s | 0 |
| Security/database/shutdown | exact selection in script: 63, 1.736s | 0 |
| Boundaries | exact selection in script: 39, 0.083s | 0 |
| Required full suite | `python -B -m unittest discover -s tests -t . -v`: **1990, 53.931s, OK, zero skips** | 0 |
| Historical Qt pair | exact pair in script, ten independent repetitions, 2 tests each, all pass | 0 |
| Ruff | `python -B -m ruff check project_akiha tests` | 0 |
| Black | `python -B -m black --check project_akiha tests` | 0 |
| Source/database/log smoke | `smoke_source_app.ps1 -SmokeRoot .../smoke-data -PythonExe .../.venv313/Scripts/python.exe` | 0 |
| Diff | `git diff --check` | 0 |

The legacy source smoke's CloseMainWindow did not request application Quit;
it reported ForcedStop=True. That run proves startup/schema/log checks only.
It is not used as graceful-shutdown evidence.

New selection (log `dist/phase13-remaining-focus.log`):

```powershell
.\.venv313\Scripts\python.exe -B -m unittest tests.unit.services.test_phase13d_reminders tests.unit.app.test_phase13d_reminders tests.unit.services.test_phase13e_information tests.unit.app.test_phase13f_navigation tests.unit.services.test_phase13g_export tests.unit.app.test_phase13_utilities tests.unit.services.test_utility_shutdown_smoke -v
```

**64 tests, 6.554s, OK, exit 0.** Independent probe/inventory reconciliation:
`python -B dist/phase13-independent-probes.py`, exit 0, captured in final evidence.

The 64-test selection consists of 19 reminder service, 4 composed reminder,
15 weather, 4 composed navigation, 14 export, 6 composed Utilities/privacy/
shutdown, and 2 isolated lifecycle-diagnostic tests. Their exact IDs are in
the reconciled `inventory.json`; all are enabled and discovered. The final
documentation-only diff check also exited 0. Implementation/test/script hashes
remain identical to the passing complete gate and candidate build inputs.

## Graceful pending-clarification shutdown

Opt-in `--utility-shutdown-smoke-report=...` uses the normal application graph,
composer and Qt aboutToQuit route. It requires a new report and a fresh isolated
`report-parent/data/Akiha` profile; an existing owner profile is rejected before
startup. It creates a normal pending folder clarification, requests Quit and
writes only boolean lifecycle evidence. It does not bypass single-instance,
permissions, IPC, GC, threads or production cleanup. Timeout/forced termination
is a failed gate. The default runtime remains unchanged.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify_utility_shutdown.ps1
```

Source proof: `dist/utility-shutdown-86fd45944312445a8638f376df4fecd7`, normal
process exit 0, all eight lifecycle checks true, log validator pass. It proves
pending lease invalidation, stopped schedule/activity timers, joined workers,
voice/background cleanup and position saving in the fresh default configuration.
It does not prove shutdown during a real active hosted/microphone session.

## Candidate and remaining checks

Build command (quality checks already passed above; only their redundant rerun
inside the builder is omitted):

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_akiha_pyinstaller.ps1 -OutputDir dist/phase13-consolidated-20261009 -WorkDir dist/phase13-consolidated-work-20261009 -Clean -SkipQualityChecks
```

The clean build passed in 138.309 seconds (PyInstaller stage 137.435s).
Candidate: `dist/phase13-consolidated-20261009/Akiha/Akiha.exe`.
Executable SHA-256:
`0d7c972e09594882333fd4e64b476dda82c9baffe136585356088982f98c816d`.
Keep the entire one-folder artifact together. Build log:
`dist/phase13-consolidated-build.log`; report:
`dist/phase13-consolidated-20261009/build-reports/pyinstaller-build-20261009-053321.json`.

| Package gate / exact invocation | Result |
| --- | --- |
| `python -B -m project_akiha.tools.verify_packaged_artifact dist/phase13-consolidated-20261009/Akiha` | Required dependencies, migrations, timezone data and forbidden private files pass, exit 0 |
| `python -B -m project_akiha.tools.verify_windows_gui_subsystem dist/phase13-consolidated-20261009/Akiha/Akiha.exe` | Windows GUI, exit 0 |
| `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/smoke_packaged_app.ps1 -ExePath dist/phase13-consolidated-20261009/Akiha/Akiha.exe -SmokeRoot dist/phase13-package-startup-20261009 -RunExistingDataPass` | Fresh/existing isolated profile, database, console-free GUI and logs pass, script exit 0; ForcedStop=True, not graceful proof |
| `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/smoke_packaged_single_instance.ps1 -ExePath dist/phase13-consolidated-20261009/Akiha/Akiha.exe -SmokeRoot dist/phase13-package-single-instance-20261009` | Primary remained running, real secondary activation handoff/exit 0; script exit 0; primary forcibly cleaned up after this IPC-only check |
| `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/verify_utility_shutdown.ps1 -ExePath dist/phase13-consolidated-20261009/Akiha/Akiha.exe -SmokeRoot dist/phase13-package-pending-shutdown-20261009` | All eight normal cleanup checks true; normal process and script exit 0; log pass; no forced termination |
| `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/test_packaged_provider_runtimes.ps1 -ExePath dist/phase13-consolidated-20261009/Akiha/Akiha.exe -ReportPath dist/phase13-consolidated-20261009/build-reports/provider-runtime-offline.json -SkipGeminiNetwork` | Isolated profile with speech disabled: frozen Google SDK import/client construction pass, exit 0. Two explicitly recorded runtime skips: real Gemini network and GPT-SoVITS; these are owner checks, not claimed live verification |
| `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/smoke_packaged_app.ps1 -ExePath dist/phase13-consolidated-20261009/Akiha/Akiha.exe -SmokeRoot dist/phase13-package-v15-upgrade-20261009` | Actual packaged startup upgrades a synthetic v15 database to v16; existing inbox ID 700 and issued-ID high water preserved; three utility tables present; logs pass; exit 0. Forced stop applies only to this startup harness |
| `python -B dist/phase13-final-evidence.py` | Implementation/test/script hashes exactly match passing source snapshot; packaged migration preservation and exact 60-file manifest pass; exit 0 |

The runtime probe accessed no owner credential/profile and started no TTS
service. Application tests have **zero skips**; runtime opt-out checks above
are distinct and remain visible. Final owner checks, including real audio,
configured shutdown/accounts/network, remain in OWNER_CHECKLIST.md. Limits:
official alerts are currently NWS coverage only; no general information browser;
active schedule labels are visible locally, terminal receipts are generic;
export needs a local filesystem supporting atomic hard links and never
overwrites; delivery is at most once, with inbox evidence when presentation
fails or is suppressed. No cross-channel retry guarantee is claimed.

13D–13H implementation and bounded agent-run review have no reproduced blocker.
13I is active pending the owner's 28-item consolidated checklist; Phase 13 is
not accepted or closed. No live provider/microphone test is represented as done.
No commit or push occurred.
The deferred 13B checks are retained here, not silently marked passed by source
startup or older 1779/1878/1924 totals.

## Exact final working-tree manifest

60 modified/new files, including the preserved 13C corrections and cleanup/handoff prerequisites. No other working-tree files were changed. Generated evidence/build files remain under ignored dist.

- `docs/audits/PHASE13C_REVIEW_2026-10-09.md`
- `docs/phases/phase-13-assistant-utilities/CONSOLIDATED_VERIFICATION.md`
- `docs/phases/phase-13-assistant-utilities/OWNER_CHECKLIST.md`
- `docs/phases/phase-13-assistant-utilities/PHASE13C.md`
- `docs/phases/phase-13-assistant-utilities/README.md`
- `docs/phases/phase-13-assistant-utilities/REMAINING_WORK.md`
- `project_akiha/app/main.py`
- `project_akiha/app/timer_delivery_controller.py`
- `project_akiha/config/__init__.py`
- `project_akiha/config/settings.py`
- `project_akiha/core/actions/clarification.py`
- `project_akiha/core/actions/permissions.py`
- `project_akiha/core/actions/registry.py`
- `project_akiha/core/actions/validation.py`
- `project_akiha/core/utilities/information.py`
- `project_akiha/core/utilities/reminders.py`
- `project_akiha/core/utilities/timers.py`
- `project_akiha/database/migrations/0016_one_shot_reminders.sql`
- `project_akiha/database/sqlite_notification_repository.py`
- `project_akiha/database/sqlite_reminder_repository.py`
- `project_akiha/database/sqlite_timer_repository.py`
- `project_akiha/services/action_clarification.py`
- `project_akiha/services/assistant_action_bridge.py`
- `project_akiha/services/config_store.py`
- `project_akiha/services/current_information.py`
- `project_akiha/services/package_artifact.py`
- `project_akiha/services/provider_health_registry.py`
- `project_akiha/services/reminder_actions.py`
- `project_akiha/services/speech_identity.py`
- `project_akiha/services/timer_schedule.py`
- `project_akiha/services/user_export.py`
- `project_akiha/services/utility_shutdown_smoke.py`
- `project_akiha/ui/action_clarification_panel.py`
- `project_akiha/ui/settings_window.py`
- `project_akiha/ui/user_export_dialog.py`
- `project_akiha/ui/utilities_panel.py`
- `pyproject.toml`
- `scripts/build_akiha_nuitka.ps1`
- `scripts/build_akiha_pyinstaller.ps1`
- `scripts/build_path_guard.ps1`
- `scripts/verify_phase13c.ps1`
- `scripts/verify_utility_shutdown.ps1`
- `tests/unit/app/test_phase13_utilities.py`
- `tests/unit/app/test_phase13c_timers.py`
- `tests/unit/app/test_phase13d_reminders.py`
- `tests/unit/app/test_phase13f_navigation.py`
- `tests/unit/core/actions/test_models_registry.py`
- `tests/unit/core/utilities/test_contracts.py`
- `tests/unit/database/test_migrator.py`
- `tests/unit/services/test_action_clarification.py`
- `tests/unit/services/test_assistant_action_bridge.py`
- `tests/unit/services/test_build_cleanup_guard.py`
- `tests/unit/services/test_gpt_sovits_engine_manager.py`
- `tests/unit/services/test_package_artifact.py`
- `tests/unit/services/test_phase13c_timers.py`
- `tests/unit/services/test_phase13d_reminders.py`
- `tests/unit/services/test_phase13e_information.py`
- `tests/unit/services/test_phase13g_export.py`
- `tests/unit/services/test_utility_shutdown_smoke.py`
- `tests/unit/ui/test_settings_window.py`

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
