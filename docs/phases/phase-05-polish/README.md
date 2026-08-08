# Phase 5 Companion Experience Polish And Interaction Depth

Phase 5 improves the feel of the companion after the core pet, chat, memory,
and behavior systems exist. It focuses on the windows, controls, history
surfaces, mood/presence feedback, and integration polish that make Akiha feel
usable as a daily desktop companion.

## Completed

- Behavior History window for inspecting recorded behavior events
- Behavior History cleanup actions for clearing all or matching events
- Settings shortcut to open Behavior History
- Tray shortcut to open Behavior History
- Chat delivery path for proactive suggestions
- Tray delivery path for proactive notifications
- Companion presence text for chat and tray surfaces
- Mood-aware visual behavior through mood-to-animation requests
- Pet menu controls for walking, sleeping, settings, and hiding
- Tray controls for show, hide, chat, settings, behavior history, and quit
- Chat UX for streaming, stopping, starting a new chat, clearing chat, and
  exporting transcripts
- Memory Manager UI for active, archived, and pending memories
- Startup and shutdown robustness review that fed into Phase 6 hardening
- Integration tests covering the proactive behavior flow
- UI tests for chat, memory, settings, tray, pet window, pet renderer, and
  behavior history windows

## Key Modules

- `project_akiha/ui/behavior_history_window.py`
- `project_akiha/ui/chat_window.py`
- `project_akiha/ui/memory_window.py`
- `project_akiha/ui/pet_window.py`
- `project_akiha/ui/settings_window.py`
- `project_akiha/ui/tray.py`
- `project_akiha/ui/proactive_delivery.py`
- `project_akiha/services/behavior_history.py`
- `project_akiha/services/transcript_export.py`
- `project_akiha/app/shutdown.py`

## Not In Phase 5

- Final 2D model art polish
- Live2D integration
- Voice input or output
- Cloud AI provider selection beyond existing mock/Ollama support
- Installer, updater, auto-start, or code signing
- Plugin API
- Local assistant command execution

## Manual Smoke Test

```powershell
python -m project_akiha.app.main
```

Then check:

- Tray and pet menu controls open the expected windows.
- Chat can stream a mock response, stop a response, start a new chat, clear the
  chat, and export a transcript.
- Memory Manager lists active, archived, and pending memories.
- Behavior History opens from Settings and tray.
- Behavior History refresh and cleanup controls do not crash.
- Presence text remains visible and coherent in chat/tray surfaces.
- Quit saves window position and does not leave active chat workers running.

## Verification

```powershell
python -m unittest discover tests
python -m compileall project_akiha tests
python -m ruff check project_akiha tests
python -m black --check project_akiha tests
```
