# Build And Release Workflow

This document captures the release workflow established in Phase 6 and updated
for the verified V5 Modular Voice Intelligence standalone package and the V8
Hosted Live release gate.

## Current Verified Candidate

The retained candidate is:

```text
dist/nuitka-v5-local-voice-final/main.dist/Akiha.exe
```

On 2026-08-08 it passed the clean Python 3.13/Nuitka build gate, packaged
artifact validation, Windows GUI subsystem validation, fresh-data and
existing-data automated smoke checks, and the complete manual startup, voice,
provider, conversation, context, action, and graceful-shutdown checklist. See
`V5_MANUAL_SMOKE_2026-08-08.md` in this folder.

The V5 folder remains the last manually verified fallback until this V8 target
passes its complete packaged checklist:

```text
dist/nuitka-v8-final/main.dist/Akiha.exe
```

The V8 candidate passed GUI-subsystem, artifact, fresh-data, existing-data,
schema, no-visible-console, and log-health automation on 2026-08-13. It remains
a candidate until the real microphone, audio, Gemini Live, Spotify, assistant
action, and Tray Quit checklist is signed off.

## Supported Python

Project Akiha declares Python `>=3.12` in `pyproject.toml`.

The recorded source validation environment is:

- Python 3.14.6 on Windows 11
- PySide6 6.11.1
- Ruff 0.15.22
- Black 26.5.1
- Nuitka 4.1.3 with Zig 0.16.0

The current release-candidate packaging environment is:

- Python 3.13.14 on Windows 11
- PySide6 6.11.1
- Ruff 0.16.0
- Black 26.5.1
- Nuitka 4.1.3 with Zig 0.16.0

Nuitka reports Python 3.14 support as experimental. Source development and
tests can continue on Python 3.14, but standalone release builds should use
Python 3.13.

Phase 6 smoke testing on 2026-07-29 found that frozen executables built with
Python 3.14.6 and Nuitka 4.1.3 can fail before Project Akiha startup logging
begins. The packaging script blocks normal builds on Python 3.14+ unless
`-AllowExperimentalPython` is supplied for diagnostics.

## Dependency Groups

Runtime install:

```powershell
pip install -e .
```

Installs the application and runtime dependencies:

- PySide6

Development install:

```powershell
pip install -e .[dev]
```

Adds tools for local development:

- Ruff
- Black

Packaging install:

```powershell
pip install -e .[package]
```

Adds everything needed by the packaging script:

- Ruff
- Black
- Nuitka

The V8 voice-enabled release package needs both local STT and Gemini Live:

```powershell
pip install -e ".[package,voice,live]"
```

## Source Run

```powershell
python -m project_akiha.app.main
```

The console script is also available after installation:

```powershell
akiha
```

## Quality Gate

Run this before packaging and before treating a release task as verified:

```powershell
.\scripts\build_akiha_nuitka.ps1 -SkipBuild
```

The script runs:

```powershell
python -m unittest discover tests
python -m ruff check project_akiha tests
python -m black --check project_akiha tests
python -m compileall project_akiha tests
python -m nuitka --version --zig --assume-yes-for-downloads
```

## Release Readiness Wrapper

Run this before the final manual packaged smoke pass:

```powershell
.\scripts\phase6_release_readiness.ps1 `
  -ExePath dist\nuitka-v8-final\main.dist\Akiha.exe `
  -RunExistingDataPass
```

The wrapper runs the quality gate, source smoke, packaged smoke when the
packaged executable exists, and creates a timestamped manual smoke report. The
report is prefilled with the package path, automated smoke results, and current
commit/worktree note.

## Source Smoke Test

Run this when startup/local-data behavior needs to be checked without creating a
standalone package:

```powershell
.\scripts\smoke_source_app.ps1
```

The source smoke script verifies:

- source app startup
- local data directory creation
- log file creation
- log health, including no unexpected `ERROR`, `CRITICAL`, or traceback lines
- SQLite database creation
- expected SQLite tables

The source smoke script is non-interactive. It may request `CloseMainWindow()`
and then force-stop the process.

## Standalone Package Build

Phase 6 established the standalone-folder artifact. V8 adds hosted-live and
provider-tool support while retaining that format. See
`docs/phases/phase-06-packaging/DISTRIBUTION_DECISION.md` for the
standalone-vs-installer decision.

```powershell
pip install -e ".[package,voice,live]"
.\scripts\build_akiha_nuitka.ps1 -OutputDir dist\nuitka-v8-final
```

Use Python 3.13 for release-candidate packaging. On Python 3.14+, the script
stops before building because that runtime is currently diagnostic-only for
Nuitka standalone output:

```powershell
.\scripts\build_akiha_nuitka.ps1 -AllowExperimentalPython
```

Only use `-AllowExperimentalPython` when investigating packaging behavior, not
when preparing a release candidate.

Create the current release-candidate environment with:

```powershell
py -3.13 -m venv .venv313
.\.venv313\Scripts\python.exe -m pip install -e ".[package,voice,live]"
$env:PATH = (Resolve-Path '.\.venv313\Scripts').Path + ';' + $env:PATH
.\scripts\build_akiha_nuitka.ps1 -OutputDir dist\nuitka-v8-final
```

The build clears Nuitka's compilation caches, then uses standalone mode,
PySide6 plugin support, Zig, attached Windows console mode, and bundled data
directories for:

- `assets`
- `project_akiha/config`
- `project_akiha/database/migrations`

After the build finishes, the script verifies that `Akiha.exe` uses the Windows
GUI subsystem instead of the Windows console subsystem.

Nuitka's `attach` mode does not create a console when Akiha is launched
normally. It can reuse an existing PowerShell console for diagnostics, which
avoids a Nuitka 4.1.3/Zig startup failure observed with `disable` mode while
still passing the no-visible-console smoke check.

The clean-cache release build is intentional. A reused Nuitka 4.1.3 module
cache produced an executable that passed artifact and subsystem validation but
failed during compiled code-object loading. Release builds trade the extra
compile time for a deterministic artifact.

The script also validates that the standalone artifact contains the expected
runtime folders, bundled assets, default config, database migrations, the
explicitly included PyAV `av.utils` extension, and faster-whisper's packaged
Silero VAD ONNX model. The V8 build also compiles the statically imported
`google.genai` modules into `Akiha.exe` for Gemini Live; packaged startup and
the local Gemini setup diagnostic verify their runtime availability. Artifact
validation rejects environment files, secret files, private Spotify exports,
and SQLite database files so credentials and `%LOCALAPPDATA%` state cannot
enter the release folder.

## Packaged Smoke Test

After a standalone build, run:

```powershell
.\scripts\smoke_packaged_app.ps1 `
  -ExePath dist\nuitka-v8-final\main.dist\Akiha.exe `
  -RunExistingDataPass
```

The smoke script verifies:

- packaged artifact contents
- Windows GUI executable subsystem
- no visible `ConsoleWindowClass` window owned by the packaged process
- packaged app startup
- local data directory creation
- log file creation
- log health, including no unexpected `ERROR`, `CRITICAL`, or traceback lines
- SQLite database creation
- expected SQLite tables
- startup with existing user config, state, and database files

The smoke script is non-interactive. It may request `CloseMainWindow()` and then
force-stop the process. Manual tray Quit validation remains required before
Phase 6 is complete.

If the packaged smoke reports that the app exited before `app.log` was created,
the failure happened before Project Akiha startup logging began. On the current
local Python 3.14.6 environment, this has been observed as a Nuitka frozen
runtime failure; rebuild with Python 3.13 before continuing release validation.
Python exceptions raised during application startup are also written
best-effort to `%LOCALAPPDATA%\Akiha\logs\startup-crash.log`.

Two small diagnostic entry points are available when investigating frozen
runtime failures:

- `scripts/diagnose_nuitka_minimal.py` checks whether a minimal frozen Python
  executable can start.
- `scripts/diagnose_nuitka_startup.py` checks frozen imports for PySide6 and
  Project Akiha startup modules.

## Manual Packaged Smoke

After automated source and packaged smoke tests pass, run the manual checklist:

```text
docs/phases/phase-06-packaging/MANUAL_PACKAGED_SMOKE.md
```

Create a timestamped manual smoke report:

```powershell
.\scripts\new_manual_smoke_report.ps1
```

The manual pass verifies real Windows UI behavior that automated offscreen tests
cannot prove, including visible console behavior, tray interactions, window
opening, drag behavior, and graceful Tray Quit.

## Lockfile Decision

Phase 7 added hosted providers and optional voice dependencies. The current
personal/local preview still uses the constraints in `pyproject.toml`, but a
locked release environment is now required before installer or public
distribution work begins. Revisit this decision before the next distributable
release rather than treating dependency resolution as reproducible today.

## Local Data Reset

Local runtime data is documented in `docs/reference/LOCAL_DATA_PRIVACY.md`.

For a full local reset, quit Akiha and remove:

```text
%LOCALAPPDATA%\Akiha\
```

## Future Backlog

Deferred ideas are organized in `docs/roadmap/PROJECT_BACKLOG.md`.
