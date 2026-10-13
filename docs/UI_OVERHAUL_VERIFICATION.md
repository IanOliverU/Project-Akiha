# Native UI overhaul verification — 2026-10-13

**Current status (2026-10-13):** UI implementation included in pushed HEAD 88a7e6b.
Phase 13I and exact-revision UI acceptance are pending under the owner's latest
instruction. See [current reconciliation](phases/phase-13-assistant-utilities/CURRENT_HEAD_VERIFICATION.md)
and [one consolidated checklist](phases/phase-13-assistant-utilities/OWNER_CHECKLIST_CURRENT_HEAD.md).
Records below are chronological history; no new commit/push occurred.


Status: implemented candidate preparation; UI and Phase 13I owner acceptance
remain pending. No commit, push or Phase 13 completion is recorded.

## Implementation and scope

The native workspace, multiline composer, local clarification card, searchable
Settings with explicit Save/draft protection, grouped Utilities, export review,
shared manager styles and grouped sprite/tray menus retain the existing Qt
controllers and operation authority. Navigation reuses existing manager windows;
Music and Utilities open their existing Settings pages. It does not replace the
application with a browser or add a parallel scheduler, chat or permission service.

The 2026-10-13 owner correction restores the committed Akiha palette. Core surface,
text, accent, hover and disabled colors are shared theme tokens. Existing semantic
status shades are preserved. `git diff --name-only -- assets/animations` is empty;
original sprite artwork was not regenerated or changed. Added SVG UI icons are
separate from sprite assets. No new dependency was installed.

Inventory and bindings: [UI_INVENTORY.md](UI_INVENTORY.md).
Feature map and design decisions: [UI_OVERHAUL.md](UI_OVERHAUL.md).

## Current source evidence

Evidence folder: `dist/ui-overhaul-palette-gates-20261013`.
Command: `powershell.exe -NoProfile -ExecutionPolicy Bypass -File
scripts/verify_phase13c.ps1 -OutputDir dist/ui-overhaul-palette-gates-20261013`.
Normal Windows execution retains real IPC and single-instance protections.

| Gate | Result |
| --- | --- |
| Inventory / compile / static core boundaries | 2,009 unique IDs; 580 Python files; exit 0 |
| Cleanup guard, including actual junction checks | 7 tests, exit 0 |
| Timer selection | 38 tests, exit 0 |
| Focused selection | 142 tests, exit 0 |
| Security/database/shutdown | 63 tests, exit 0 |
| Boundary selection | 39 tests, exit 0 |
| Required single-process complete discovery | 2,009 tests in 110.480s, no skips, OK, exit 0 |
| Historical Qt pair | 10 repetitions, two tests each, exit 0 each |
| Black check | 580 files unchanged, exit 0 |
| Source/database/log startup smoke | exit 0; startup cleanup forcibly stopped process |
| Git diff check | exit 0 |

The combined runner exit was 1 solely because Ruff found two import-order issues
in menus.py and test_ui_overhaul.py. Both were corrected without changing behavior.
`python -B -m ruff check project_akiha tests` then exited 0 (ruff-final.log).
`python -B -m black --check project_akiha tests` then exited 0 (black-final.log).
The affected rerun `python -B -m unittest tests.unit.ui.test_ui_overhaul
tests.unit.app.test_ui_overhaul tests.unit.ui.test_settings_window -v` passed
46 tests in 8.911s, exit 0 (ui-final.log). Full discovery was not unnecessarily
repeated for import ordering. Preserve the original failing Ruff record.

The new UI tests cover multiline send/insertion/streaming, stable scroll and
selection, local navigation, static-only Settings search, preserved drafts,
Save errors, close cancellation, weather presentation, native reminder inputs,
snapshot-only export selection, accessible vector icons, menu overflow and exact
original palette values. Three composed tests use the real application graph.
The package regression requires bundled icons and QtSvg runtime files.

Presentation correction manifest (existing Phase 13 utility changes are retained
separately in the consolidated record):

- `project_akiha/app/main.py`: workspace routing, clarification placement,
  truthful Settings save failure and draft-aware Quit.
- `project_akiha/ui/{theme,components,fluent_icons,menus}.py`: shared tokens,
  native components/vector icons and scrollable grouped menus.
- `project_akiha/ui/{chat_window,action_clarification_panel,settings_window}.py`:
  workspace/composer, local card, static search and explicit draft protection.
- `project_akiha/ui/{utilities_panel,user_export_dialog,music_files_panel}.py`:
  native grouped utility inputs, snapshot export review and responsive music actions.
- `project_akiha/ui/{manager_presentation,pet_window,tray,privacy_notice}.py`:
  shared manager surfaces, unchanged sprite commands, menus and native notice.
- `project_akiha/services/package_artifact.py` and
  `tests/unit/services/test_package_artifact.py`: required SVG icons/QtSvg bundle.
- `tests/unit/{ui,app}/test_ui_overhaul.py`: new interaction/composition regressions.
  Existing Settings assertions are retained in `test_settings_window.py`.
- `assets/ui/icons/*.svg`: 24 local vector UI icons, separate from sprite art.
- `docs/UI_{INVENTORY,OVERHAUL,OWNER_CHECKLIST,OVERHAUL_VERIFICATION}.md` and
  Phase 13 README/OWNER_CHECKLIST: inventory, design, evidence and pending testing.

The full current working-tree manifest, including preserved Phase 13 work, is
captured in `dist/ui-overhaul-manifest-20261013.txt`; no generated evidence or
private data is proposed for a future commit.

Sandbox attempts exposed temporary-directory cleanup denial and a stalled
application-composition run. They are not passing evidence; normal Windows
reruns above did not disable IPC, garbage collection or single-instance protection.

## Lifecycle and visual evidence

`scripts/verify_utility_shutdown.ps1 -SmokeRoot
dist/ui-overhaul-source-shutdown-20261013` passed, exit 0. Its isolated synthetic
pending clarification was invalidated on Quit; schedule/activity ticks stopped,
workers joined, voice/background workers stopped and position saved. This is
default-profile diagnostic evidence, not live configured-cloud/TTS verification.

Native Windows Qt screenshots using synthetic temporary data:
`dist/ui-overhaul-review/original-palette-windows-100` and variants
`original-palette-windows-1.25`, `-1.5`, `-2`. Capture commands exited 0.
Chat, Settings, clarification, reminder/weather, managers and sprite menu were
captured. These are Qt scale-factor checks; actual owner Windows DPI settings
remain checklist items. Large menus use native scrolling and keyboard navigation.

Readable comparison screenshots in `before-committed-windows` show the committed
pre-overhaul UI, rather than every earlier uncommitted utility screen.

## Candidate and owner testing

Fresh candidate packaging and package-specific evidence are recorded below when
finished. Older UI and Phase 13 candidates are superseded for new owner testing.
Use [UI_OWNER_CHECKLIST.md](UI_OWNER_CHECKLIST.md) and the retained
[Phase 13 checklist](phases/phase-13-assistant-utilities/OWNER_CHECKLIST.md).
Real microphone, provider/cloud audio, configured TTS, OAuth/playback and actual
Windows DPI checks remain owner testing. No manual acceptance is inferred.

The first 2026-10-13 package failed before UI startup (QtCore DLL procedure error).
Its PyInstaller COLLECT record proved `icuuc.dll` came from Codex's Poppler
runtime on inherited PATH. That ICU exports version-suffixed symbols, while Qt
uses the Windows system ICU API. Temporarily moving only that generated DLL out
of loader search made the isolated packaged shutdown diagnostic pass, exit 0;
the DLL was then restored. Preserve the failed startup/IPC/shutdown evidence.
This is a packaging-environment collision, not a palette or application defect.

The replacement build uses a process-local PATH containing only venv/Python,
Windows, System32 and WindowsPowerShell/v1.0. It changes no installed dependency,
configuration or application implementation. Output/work directories are new
guarded paths: `dist/ui-overhaul-candidate-20261013-final` and
`dist/ui-overhaul-work-20261013-final`. The first candidate must not be delivered.

## Replacement candidate results

Candidate: `dist/ui-overhaul-candidate-20261013-final/Akiha/Akiha.exe`.
Keep the entire Akiha directory together. SHA-256:
`c93c56c5706df74b5862afb4ba93e5782425c197f4059e3ed50af3bcbfe92e7c`.
Guarded clean build, artifact and Windows GUI validation exited 0; build duration
115.899s. Redundant build quality checks were omitted after the source gates above.
The final COLLECT record contains no bundled Poppler `icuuc.dll`.

Exact supported package commands (all exit 0):

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/smoke_packaged_app.ps1 -ExePath dist/ui-overhaul-candidate-20261013-final/Akiha/Akiha.exe -SmokeRoot dist/ui-overhaul-package-smoke-20261013-final -RunExistingDataPass
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/smoke_packaged_single_instance.ps1 -ExePath dist/ui-overhaul-candidate-20261013-final/Akiha/Akiha.exe -SmokeRoot dist/ui-overhaul-package-ipc-20261013-final
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/verify_utility_shutdown.ps1 -ExePath dist/ui-overhaul-candidate-20261013-final/Akiha/Akiha.exe -SmokeRoot dist/ui-overhaul-package-shutdown-20261013-final
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/test_packaged_provider_runtimes.ps1 -ExePath dist/ui-overhaul-candidate-20261013-final/Akiha/Akiha.exe -ReportPath dist/ui-overhaul-candidate-20261013-final/build-reports/provider-runtime-offline.json -SkipGeminiNetwork
```

The first command used venv Python first on PATH for schema/log verification.
The offline runtime command used isolated LOCALAPPDATA/APPDATA and disabled voice;
Gemini SDK import/client construction passed, while live Gemini connection and
GPT-SoVITS health were explicitly skipped (two runtime checks, not unittest skips).
Startup/schema/log smoke force-terminates during cleanup and does not prove
graceful shutdown. The separate pending-clarification diagnostic proves normal
process exit 0 and all eight lifecycle checks with the packaged default temporary
profile. Single-instance activation handed off with secondary exit 0.
Configured owner voice/network shutdown remains a manual checklist requirement.

Before/after comparison: `dist/ui-overhaul-review/before-committed-windows` versus
`dist/ui-overhaul-review/original-palette-windows-100`. Additional native captures
cover 125%, 150% and 200% Qt scaling. Owner Windows scaling, live account/voice
flows and existing private-profile acceptance remain pending; no pass is inferred.

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

## Final owner-requested chat presentation correction

On 2026-10-13, removed per-message background fills from ordinary and streamed
chat, retaining spacing, speaker colors, escaping and subtitle privacy. Actual
composed native capture `dist/ui-overhaul-review/no-chat-highlights-20261013/chat.png`
confirms the unhighlighted presentation. `python -B -m unittest
tests.unit.ui.test_ui_overhaul tests.unit.ui.test_chat_window -v` passed 48 tests
in 2.027s, exit 0; Ruff for all source/tests and Black for chat_window.py passed.
The 2,009-test full run and package evidence above predate this cosmetic change;
they are not represented as newly rerun. The previously delivered package retains
the old highlights; the source checkpoint contains the final correction.
