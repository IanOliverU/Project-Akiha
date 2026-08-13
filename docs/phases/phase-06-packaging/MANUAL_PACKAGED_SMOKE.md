# Manual Packaged Smoke Checklist

Use this checklist after a fresh standalone package build and automated packaged
smoke pass.

Create a timestamped report before starting the manual pass:

```powershell
.\scripts\new_manual_smoke_report.ps1
```

The script copies
`docs/phases/phase-06-packaging/MANUAL_SMOKE_REPORT_TEMPLATE.md` into
`dist\manual-smoke-reports\`.

## Prerequisites

Use a standalone package built with Python 3.13 for release-candidate manual
smoke testing. Python 3.14 packaging is currently diagnostic-only because Phase
6 found non-runnable Nuitka frozen executables on Python 3.14.6.

Build the standalone package:

```powershell
pip install -e ".[package,voice,live]"
.\scripts\build_akiha_nuitka.ps1 `
  -CleanRelease `
  -OutputDir dist\nuitka-phase9-final
```

Run the automated packaged smoke:

```powershell
.\scripts\smoke_packaged_app.ps1 `
  -ExePath dist\nuitka-phase9-final\main.dist\Akiha.exe `
  -RunExistingDataPass
```

Then launch the packaged app manually:

```text
dist\nuitka-phase9-final\main.dist\Akiha.exe
```

## First-Run Privacy

- [ ] With fresh local config, the versioned privacy notice appears.
- [ ] The notice accurately describes push-to-talk capture, local providers,
  optional hosted processing, and encrypted hosted credentials.
- [ ] Clicking **I understand** continues startup normally.
- [ ] After quitting and relaunching, the acknowledged notice does not appear
  again.

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

## Voice

- [ ] **Check setup** reports the configured STT and TTS providers accurately.
- [ ] **Test microphone** captures and transcribes speech.
- [ ] Live transcription appears while speaking.
- [ ] A final transcript auto-sends when that option is enabled.
- [ ] **Test voice** synthesizes and plays the Japanese test phrase.
- [ ] Automatic reply speech works when enabled.
- [ ] Stop voice interrupts playback without crashing.
- [ ] Listening, thinking, speaking, muted, and error states remain coherent.
- [ ] A configured standalone VOICEVOX Engine starts in the background.
- [ ] Quitting Akiha stops only a VOICEVOX process that Akiha started.
- [ ] An externally started VOICEVOX process remains running after Akiha quits.

## Conversation Lanes

- [ ] Local Modular Talk transcribes, sends, and speaks one turn.
- [ ] Local Modular Conversation returns to listening after each reply.
- [ ] Gemini Live starts only after explicit Cloud selection and consent.
- [ ] Gemini Live shows final user and assistant transcripts in Chat.
- [ ] Gemini Live plays native audio without an unexpected traceback.
- [ ] Speaking during Gemini playback interrupts stale output safely.
- [ ] Gemini Live returns to listening after ordinary replies and tool results.
- [ ] Ending Cloud Conversation stops microphone and provider ownership.
- [ ] A Cloud failure remains visible and never silently starts Local Modular.

## Assistant Actions

- [ ] A missing application or path permission is denied and audited.
- [ ] An approved application such as Discord, Chrome, Spotify, or VS Code opens.
- [ ] An approved directory and one nested directory open.
- [ ] A passive local media file requires confirmation before opening.
- [ ] Spotify search, playback, pause/resume, volume, shuffle, seeking, playlist,
  and artist-page actions work with a connected Premium account.
- [ ] Ambiguous local or Spotify results remain visible only in local UI.
- [ ] `result N` selects the intended local result without exposing its path or
  Spotify URI to Gemini.
- [ ] Assistant Action History shows the sanitized result and no credentials,
  file contents, or unrestricted exception text.

## Memory Manager

- [ ] Memory Manager opens from Settings.
- [ ] Active memories list renders.
- [ ] Archived memories list renders.
- [ ] Pending memories list renders.
- [ ] Refresh does not crash.
- [ ] Edit/archive/restore/delete/clear actions still match
  `docs/reference/LOCAL_DATA_PRIVACY.md`.
- [ ] With mock AI and memory approval enabled, sending
  `私の名前はテストユーザーです。` creates the pending memory
  `ユーザーの名前はテストユーザーです`.
- [ ] The Japanese test memory can be rejected cleanly after verification.

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
