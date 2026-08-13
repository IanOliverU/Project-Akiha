# Build And Release Workflow

This document captures the release workflow established in Phase 6 and updated
for the verified V8 Hosted Live standalone package.

## Current Verified Candidate

The retained verified package is:

```text
dist/nuitka-v8-final/main.dist/Akiha.exe
```

On 2026-08-13 it passed the Python 3.13/Nuitka build gate, packaged-artifact and
Windows GUI subsystem validation, fresh-data and existing-data automated smoke,
and the complete real-device microphone, Gemini Live, local fallback, provider
tool, Spotify, transcript, and graceful-shutdown checklist. See
`V8_MANUAL_SMOKE_2026-08-13.md` in this folder. Older executable folders and
compiler trees were removed after this package was accepted.

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
.\scripts\build_akiha_nuitka.ps1 `
  -FastBuild `
  -OutputDir dist\nuitka-dev
```

`-FastBuild` is the normal packaged-development lane. It reuses Nuitka's
standard development cache and is appropriate for debugging packaged-only
behavior during a phase. The first build on a machine is still cold, but later
builds can reuse unchanged C compiler results.

Use a clean build only when closing a phase or preparing a release candidate:

```powershell
.\scripts\build_akiha_nuitka.ps1 `
  -CleanRelease `
  -OutputDir dist\nuitka-phase9-final
```

The script requires one of these modes for every real package build. It rejects
commands that provide both modes or neither mode.

Use Python 3.13 for release-candidate packaging. On Python 3.14+, the script
stops before building because that runtime is currently diagnostic-only for
Nuitka standalone output:

```powershell
.\scripts\build_akiha_nuitka.ps1 `
  -FastBuild `
  -AllowExperimentalPython `
  -OutputDir dist\nuitka-experimental
```

Only use `-AllowExperimentalPython` when investigating packaging behavior, not
when preparing a release candidate.

Create the current release-candidate environment with:

```powershell
py -3.13 -m venv .venv313
.\.venv313\Scripts\python.exe -m pip install -e ".[package,voice,live]"
$env:PATH = (Resolve-Path '.\.venv313\Scripts').Path + ';' + $env:PATH
.\scripts\build_akiha_nuitka.ps1 `
  -CleanRelease `
  -OutputDir dist\nuitka-phase9-final
```

Both modes use standalone mode, PySide6 plugin support, Zig, attached Windows
console mode, and bundled data directories for:

- `assets`
- `project_akiha/config`
- `project_akiha/database/migrations`

After the build finishes, the script verifies that `Akiha.exe` uses the Windows
GUI subsystem instead of the Windows console subsystem.

Nuitka's `attach` mode does not create a console when Akiha is launched
normally. It can reuse an existing PowerShell console for diagnostics, which
avoids a Nuitka 4.1.3/Zig startup failure observed with `disable` mode while
still passing the no-visible-console smoke check.

The build caches are intentionally separated:

- `-FastBuild` uses Nuitka's reusable development cache under
  `%LOCALAPPDATA%\Nuitka\Nuitka\Cache` by default.
- `-CleanRelease` uses
  `%LOCALAPPDATA%\Akiha\BuildCache\Nuitka\release` and applies
  `--clean-cache=all` only to that release cache.

The clean release lane is intentional. A reused Nuitka 4.1.3 module cache
produced an executable that passed artifact and subsystem validation but failed
during compiled code-object loading. Final phase and release builds trade the
extra compile time for a deterministic artifact without destroying the cache
used by development builds.

Each command records per-stage and total durations in:

```text
<output-dir>\build-reports\build-timings-<timestamp>.json
```

Every real package build also writes Nuitka's dependency and compilation report
to:

```text
<output-dir>\build-reports\nuitka-compilation-report-<timestamp>.xml
```

The console prints the same stage-duration summary after success or failure.

### Cached Build Benchmark

The first measured `-FastBuild` candidate was created on 2026-08-13 with
Python 3.13.14, Nuitka 4.1.3, Zig 0.16.0, and the reusable development cache:

```text
dist\nuitka-fast-benchmark\main.dist\Akiha.exe
```

Results:

- Nuitka availability: 1.277 seconds
- Nuitka standalone build: 456.267 seconds, or 7 minutes 36 seconds
- Windows GUI subsystem validation: 0.277 seconds
- Packaged artifact validation: 0.214 seconds
- Output: 193 files totaling 393.7 MB
- Fresh-data packaged smoke: passed
- Existing-data packaged smoke: passed

The previous clean V8 build took approximately five hours on the same project.
The measured cached development build was therefore about 39 times faster.
This benchmark does not weaken the release rule: phase-closing and distributable
candidates still use `-CleanRelease` and receive the full manual smoke pass.

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
