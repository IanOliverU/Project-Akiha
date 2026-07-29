# Manual Packaged Smoke Checklist

Use this checklist after a fresh standalone package build and automated packaged
smoke pass.

Create a timestamped report before starting the manual pass:

```powershell
.\scripts\new_manual_smoke_report.ps1
```

The script copies `docs/MANUAL_SMOKE_REPORT_TEMPLATE.md` into
`dist\manual-smoke-reports\`.

## Prerequisites

Use a standalone package built with Python 3.13 for release-candidate manual
smoke testing. Python 3.14 packaging is currently diagnostic-only because Phase
6 found non-runnable Nuitka frozen executables on Python 3.14.6.

Build the standalone package:

```powershell
pip install -e .[package]
.\scripts\build_akiha_nuitka.ps1
```

Run the automated packaged smoke:

```powershell
.\scripts\smoke_packaged_app.ps1 `
  -ExePath dist\nuitka\main.dist\Akiha.exe `
  -RunExistingDataPass
```

Then launch the packaged app manually:

```text
dist\nuitka-phase6-py313\main.dist\Akiha.exe
```

## Visual Startup

- [ ] The app starts without a visible console window.
- [ ] The pet appears on the desktop.
- [ ] The pet image is not blank.
- [ ] The pet is draggable.
- [ ] Dragging the pet does not leave visual artifacts.

Automated packaged smoke already checks the executable subsystem and verifies
that the running process does not own a visible Windows console window. This
manual check is still kept as a human visual confirmation.

## Tray Controls

- [ ] The Project Akiha tray icon appears.
- [ ] Tray Show shows the pet.
- [ ] Tray Hide hides the pet.
- [ ] Tray Chat opens the Chat window.
- [ ] Tray Settings opens the Settings window.
- [ ] Tray Behavior History opens the Behavior History window.
- [ ] Tray Quit exits the app.

## Settings Window

- [ ] Settings opens from tray.
- [ ] Settings opens from pet menu if available.
- [ ] Changing a harmless setting and saving does not crash.
- [ ] Open logs opens `%LOCALAPPDATA%\Akiha\logs\`.
- [ ] Open data opens `%LOCALAPPDATA%\Akiha\`.
- [ ] Reset position moves/saves the pet position.

## Chat Window

- [ ] Chat opens from tray.
- [ ] Chat opens from pet menu if available.
- [ ] Sending a message with the mock provider returns a response.
- [ ] Stop cancels an active response without crashing.
- [ ] New chat starts a fresh conversation.
- [ ] Clear chat clears the current transcript after confirmation.
- [ ] Export writes a readable transcript to a selected file.

## Memory Manager

- [ ] Memory Manager opens from Settings.
- [ ] Active memories list renders.
- [ ] Archived memories list renders.
- [ ] Pending memories list renders.
- [ ] Refresh does not crash.
- [ ] Edit/archive/restore/delete/clear actions still match
  `docs/LOCAL_DATA_PRIVACY.md`.

## Behavior History

- [ ] Behavior History opens from tray.
- [ ] Behavior History opens from Settings.
- [ ] Refresh does not crash.
- [ ] Clear all does not crash.
- [ ] Clear matching does not crash.

## Proactive Behavior

- [ ] Leaving the app running does not crash when timers tick.
- [ ] Quiet-hours/cooldown settings still save from Settings.
- [ ] Proactive chat/tray delivery does not interrupt shutdown.

## Graceful Quit

- [ ] Move the pet to a visible new position.
- [ ] Start a chat response, then use Stop or Quit.
- [ ] Quit from tray.
- [ ] The process exits without needing Task Manager.
- [ ] `%LOCALAPPDATA%\Akiha\state\pet_window.json` is written.
- [ ] Relaunching the app restores/clamps the saved pet position.
- [ ] `%LOCALAPPDATA%\Akiha\logs\app.log` includes
  `Shutdown cleanup complete`.

## Pass Criteria

The manual packaged smoke passes when every checked item above succeeds and the
app log contains no unexpected startup, provider, migration, or shutdown
tracebacks.

Record the final result in the generated manual smoke report.

Known acceptable caveat:

- Automated smoke scripts may force-stop the app after requesting
  `CloseMainWindow()`. This does not replace the manual Tray Quit check.

## Failure Capture

If a check fails, capture:

- the exact step that failed
- a screenshot if the failure is visual
- `%LOCALAPPDATA%\Akiha\logs\app.log`
- whether the failure happened from source or packaged app
- whether `%LOCALAPPDATA%\Akiha\` was fresh or reused
