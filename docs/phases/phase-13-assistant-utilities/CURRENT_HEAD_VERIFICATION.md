# Exact-revision reconciliation - 2026-10-13

Current source HEAD: `88a7e6b56322759570dc0c9ee5c72b9fbf88a147` (main).
Phase 13 is pending renewed acceptance checks at the owner's request after the
push. The earlier owner functional approval/closure is preserved as historical
evidence, not erased or treated as item-level results for this fresh candidate.
No later phase starts; no implementation change, feature, commit or push is part
of this reconciliation. Working-tree changes are documentation only.

## Evidence retained and reconciled

The UI overhaul is included in HEAD. The previous package predates the final
chat-background removal and cannot establish the current screen's behavior.

`dist/phase13-head-88a7e6b-evidence-20261013/reconciliation.json` compares captured
implementation/test/script SHA-256 values with current files:

- `ui-overhaul-palette-gates-20261013`: 614 matching files, three changed files:
  chat_window.py (background removal), menus.py and test_ui_overhaul.py (import
  ordering, separately checked after Ruff findings).
- `ui-overhaul-final-inventory-20261013`: 616 matching files; only chat_window.py
  changed afterward. No other implementation/script/test change is unaccounted for.
- Current discovery: exactly 2,009 unique IDs, matching the previous inventory.
  The last full single-process run remains **2,009 tests, 110.480s, no skips,
  exit 0**. It is retained evidence with the above reconciliation, not described
  as a new full-suite run at HEAD.
- The seven real cleanup/junction checks, ten Qt-pair repetitions, 38 timer,
  142 focused, 63 security/database/shutdown and 39 boundary tests remain passing
  evidence. Unchanged source compilation/static boundaries and migrations are
  retained. No tests, IPC protections, garbage collection or guard were weakened.
- The combined historical runner's exit 1 came from two Ruff import-order
  findings, corrected and independently rechecked; its full-test exit was 0.
  Preserve both the failure record and the succeeding Ruff/Black records.
- Prior package graceful shutdown/source proof remains historical default-profile
  evidence. Live configured voice/cloud behavior was not established by SDK mocks
  or two explicitly skipped runtime checks.

## Exact-HEAD affected-flow verification

Evidence: `dist/phase13-head-88a7e6b-evidence-20261013`.

```powershell
.\.venv313\Scripts\python.exe -B -m unittest tests.unit.ui.test_ui_overhaul tests.unit.ui.test_chat_window tests.unit.ui.test_settings_window tests.unit.app.test_ui_overhaul tests.unit.app.test_phase13_utilities tests.unit.app.test_phase13b_composition -v
.\.venv313\Scripts\python.exe -B -m ruff check project_akiha tests
.\.venv313\Scripts\python.exe -B -m black --check project_akiha/ui/chat_window.py
```

Normal Windows execution with temporary data beneath the evidence folder:
**101 tests, 25.327s, no skips, exit 0**; Ruff exit 0; chat Black check exit 0.
This covers real composed navigation, save-error/draft-aware Quit, timer/weather/
export controls, actual composer/ChatController persistence privacy, local-search
ownership, streaming/multiline/selection, native reminder inputs, menu overflow
and palette. The suite was not rerun in full for a cosmetic background removal.

Native Windows Qt synthetic captures at this revision are in `native-captures`;
capture exit 0. The chat shows no highlight strips. Source captures verify native
layout; they are not evidence of real microphone/provider or owner DPI checks.

## Fresh candidate

Output: `dist/phase13-head-88a7e6b-candidate-20261013/Akiha/Akiha.exe`.
The candidate uses the exact HEAD implementation; documentation reconciliation
is uncommitted and does not modify runtime code. Build evidence and dependency
checks are recorded below when complete. Never substitute the older candidate.

The build uses the verified guarded clean path, a new non-overlapping work
directory and a process-local Windows/Python PATH excluding Codex Poppler's
conflicting ICU DLL. Source gates above and unchanged full-suite evidence justify
omitting redundant build quality checks, not omitting artifact validation.

## Outstanding acceptance only

Use [one consolidated checklist](OWNER_CHECKLIST_CURRENT_HEAD.md), covering the
new package's final Chat appearance, native scaling/keyboard/drafts/navigation,
retained local choices/privacy and utility/export controls, configured voice/TTS/
Gemini suspension and graceful configured-session Quit. Prior utility functional
approval is preserved; automatic checks are not reclassified as manual testing.
Unchanged expiry/race/DST/migration/security fixtures need no owner repetition.
N/A required checks need explicit resolution, not an assumed pass. Phase 13I
remains pending until fresh-candidate checks and owner results are reconciled.

## Fresh package results

Build, artifact and Windows GUI checks exited 0; PyInstaller build stage took
136.945s. EXE SHA-256:
`30edd4f920b7c2626dc2cad24f0144989bf45e33925de4fccf7642b9066bbb6d`.
The candidate's embedded `_message_html` bytecode/constants/names match the
current HEAD renderer and contain no background-color fill (embedded-chat.log,
exit 0). Thus the changed screen is bound to the new artifact; no old package is
substituted. This static binding complements source captures and package startup,
but is not manual visual acceptance.

Commands and results, using isolated temporary application data:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/build_akiha_pyinstaller.ps1 -OutputDir dist/phase13-head-88a7e6b-candidate-20261013 -WorkDir dist/phase13-head-88a7e6b-work-20261013 -Clean -SkipQualityChecks
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/smoke_packaged_app.ps1 -ExePath dist/phase13-head-88a7e6b-candidate-20261013/Akiha/Akiha.exe -SmokeRoot dist/phase13-head-88a7e6b-smoke-20261013 -RunExistingDataPass
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/smoke_packaged_single_instance.ps1 -ExePath dist/phase13-head-88a7e6b-candidate-20261013/Akiha/Akiha.exe -SmokeRoot dist/phase13-head-88a7e6b-ipc-20261013
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/verify_utility_shutdown.ps1 -ExePath dist/phase13-head-88a7e6b-candidate-20261013/Akiha/Akiha.exe -SmokeRoot dist/phase13-head-88a7e6b-shutdown-20261013
```

All four commands exited 0. The build used the isolated PATH described above;
the schema/log smoke used venv Python first on PATH. SmokeRoot paths must be new
if owner reruns a diagnostic. Fresh/existing startup verifies package/GUI/data/
schema/logs; its forced cleanup is not graceful-shutdown evidence. The separate
shutdown process exited normally with all eight checks true: pending action
existed then invalidated, schedule/activity ticks stopped, workers joined,
voice/background work stopped and position saved. It uses a default isolated
profile, leaving configured local/cloud/TTS session testing outstanding.
Single-instance activation kept the primary running and secondary exited 0.

Unchanged provider SDK/offline evidence remains retained; real microphone,
Gemini Live and GPT-SoVITS were not exercised by these commands. No old failures
or skipped runtime checks were relabeled as passed. No new implementation,
test-suite split, guard relaxation, commit or push occurred.
