# Build And Release Workflow

This document captures the Phase 6 build workflow for Project Akiha.

## Supported Python

Project Akiha declares Python `>=3.12` in `pyproject.toml`.

The current Phase 6 validation environment is:

- Python 3.14.6 on Windows 11
- PySide6 6.11.1
- Ruff 0.15.22
- Black 26.5.1
- Nuitka 4.1.3 with Zig 0.16.0

Nuitka reports Python 3.14 support as experimental. Local validation can
continue on Python 3.14, but use Python 3.13 for a public release candidate if
Nuitka packaging instability appears.

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

## Source Run

```powershell
python -m project_akiha.app.main
```

The console script is also available after installation:

```powershell
akiha
```

## Quality Gate

Run this before packaging and before treating a Phase 6 task as verified:

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

The first Phase 6 release artifact is a standalone folder. See
`docs/DISTRIBUTION_DECISION.md` for the standalone-vs-installer decision.

```powershell
pip install -e .[package]
.\scripts\build_akiha_nuitka.ps1
```

The build uses Nuitka standalone mode, PySide6 plugin support, Zig, disabled
Windows console mode, and bundled data directories for:

- `assets`
- `project_akiha/config`
- `project_akiha/database/migrations`

After the build finishes, the script verifies that `Akiha.exe` uses the Windows
GUI subsystem instead of the Windows console subsystem.

The script also validates that the standalone artifact contains the expected
runtime folders, bundled assets, default config, and database migrations.

## Packaged Smoke Test

After a standalone build, run:

```powershell
.\scripts\smoke_packaged_app.ps1 `
  -ExePath dist\nuitka\main.dist\Akiha.exe `
  -RunExistingDataPass
```

The smoke script verifies:

- packaged artifact contents
- Windows GUI executable subsystem
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

## Manual Packaged Smoke

After automated source and packaged smoke tests pass, run the manual checklist:

```text
docs/MANUAL_PACKAGED_SMOKE.md
```

Create a timestamped manual smoke report:

```powershell
.\scripts\new_manual_smoke_report.ps1
```

The manual pass verifies real Windows UI behavior that automated offscreen tests
cannot prove, including visible console behavior, tray interactions, window
opening, drag behavior, and graceful Tray Quit.

## Lockfile Decision

No lockfile workflow is being added in Phase 6. The project is still small, and
the current dependency constraints in `pyproject.toml` are sufficient for local
development and packaging validation.

Revisit a lockfile when any of these become true:

- cloud providers are added
- voice dependencies are added
- installer distribution begins
- reproducible public release builds become a requirement
- dependency resolution starts changing behavior between machines

## Local Data Reset

Local runtime data is documented in `docs/LOCAL_DATA_PRIVACY.md`.

For a full local reset, quit Akiha and remove:

```text
%LOCALAPPDATA%\Akiha\
```
