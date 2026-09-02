# Phase 12 Manual Smoke Checklist

**Candidate:** `dist/pyinstaller-phase12/Akiha/Akiha.exe`

**Status:** Passed - owner accepted the packaged candidate on 2026-09-02.

## Automated Evidence

- [x] 1,684 tests passed with 3 expected skips.
- [x] Ruff, Black, compileall, migration, and diff checks passed.
- [x] Cached PyInstaller one-folder build completed in 114.570 seconds.
- [x] Artifact privacy/dependency and Windows GUI-subsystem checks passed.
- [x] Fresh-data and existing-data startup passed with migration `0014` and a
  clean privacy-safe log.
- [x] A second packaged launch exited with code 0 while the primary remained
  active and accepted the activation handoff.
- [x] Real packaged Gemini SDK import and Gemini Live session open/close passed.
- [x] Real packaged GPT-SoVITS health and in-memory synthesis passed.
- [x] Deterministic tests cover inbox retention/read/clear behavior, bounded
  queue overflow, aggregation, per-event channels, provider failure, and bounded
  GPT-SoVITS recovery.

The startup automation stops the transparent tray application by exact process
ID after inspection because it cannot operate the tray menu. That forced test
cleanup is not evidence of a graceful user shutdown; the tray-exit check remains
manual below.

## Owner Acceptance

- [x] Launch `Akiha.exe` and confirm the pet and tray appear without a console
  window or duplicate process.
- [x] Open Settings and confirm the bounded provider-health summary appears
  without credentials, message content, or private paths.
- [x] Open **Notifications** from Settings or the tray, then verify refresh,
  mark-read, mark-all-read, and clear controls.
- [x] Send one new Gmail test message and confirm one sanitized Notification
  Center row plus the configured visual/chat/voice delivery.
- [x] Send one Discord bot DM or authorized mention and confirm one sanitized
  Notification Center row plus the configured delivery.
- [x] Confirm repeated unique events defer or aggregate while Akiha is speaking
  instead of disappearing; confirm one exact provider event stays deduplicated.
- [x] Set one event category to visual-only and confirm it does not speak; return
  the setting to the preferred channel mode afterward.
- [x] Start one Local Modular conversation and confirm recognition and
  GPT-SoVITS playback remain responsive.
- [x] Quit through Akiha's tray menu and confirm the application and owned
  provider process close without Task Manager.
- [x] Relaunch once and confirm previously handled Gmail/Discord events are not
  announced again.

The owner accepted these packaged interaction checks and formally closed Phase
12 on 2026-09-02.
