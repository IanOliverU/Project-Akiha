# Phase 1 Desktop Pet

Phase 1 is the non-AI desktop pet foundation. It is intentionally scoped to a
small, runnable Windows-first app with interaction, settings, persistence,
logging, and sprite asset loading.

## Completed

- Transparent frameless PySide6 pet window
- Dragging
- Right-click pet actions: Walk, Stop walking, Sleep, Wake, Settings, Hide
- System tray actions: Show, Hide, Settings, Quit
- Settings window for Phase 1 pet options
- User config saved to `%LOCALAPPDATA%\Akiha\user_config.toml`
- Pet position saved to `%LOCALAPPDATA%\Akiha\state\pet_window.json`
- Rotating app logs at `%LOCALAPPDATA%\Akiha\logs\app.log`
- Restored window position clamped to visible screen bounds
- Framework-free EventBus and animation state machine
- Application controller between UI events and core state
- Animation provider interface
- Placeholder animation provider and renderer
- TOML sprite animation manifest loader
- QPixmap sprite renderer with placeholder fallback
- Example and active animation manifests under `assets/animations/`
- Unit tests, compile pass, ruff, and black checks

## Not In Phase 1

- AI chat
- Ollama integration
- memory/database
- assistant commands
- automation permissions
- voice
- plugins
- Live2D

## Manual Smoke Test

```powershell
python -m project_akiha.app.main
```

Then check:

- The pet appears.
- Dragging works.
- Right-click menu can Sleep/Wake, Walk/Stop walking, and open Settings.
- Tray can Show/Hide/Settings/Quit.
- Settings Save persists values across restart.
- Reset position moves the pet back to the configured start position.
- Open logs opens the log directory.

## Verification

```powershell
python -m unittest discover tests
python -m compileall project_akiha tests
python -m ruff check project_akiha tests
python -m black --check project_akiha tests
```
