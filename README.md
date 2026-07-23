# Project Akiha

Project Akiha is a Windows-first desktop companion app. Phase 1 is the desktop
pet foundation: a transparent PySide6 pet window, tray controls, settings,
position persistence, logging, and sprite animation loading without AI yet.

## Run

```powershell
python -m project_akiha.app.main
```

Install dependencies first if needed:

```powershell
pip install -e .[dev]
```

## Phase 1 Features

- Drag the pet around the desktop.
- Right-click the pet for Walk, Stop walking, Sleep, Wake, Settings, and Hide.
- Use the tray for Show, Hide, Settings, and Quit.
- Edit Phase 1 settings without hand-editing TOML.
- Load sprite frames from `assets/animations/manifest.toml`.
- Fall back to the placeholder renderer if sprite assets are missing.

Phase 1 details live in `docs/PHASE1_DESKTOP_PET.md`.

## Phase 2 Status

Phase 2 has started with a chat window and local mock AI provider. This is not
Ollama yet; it is the UI/controller/provider foundation for companion chat.

- Open Chat from the tray menu.
- Open Chat from the pet right-click menu.
- Send a message and receive a deterministic mock response.

Phase 2 details live in `docs/PHASE2_CHAT_FOUNDATION.md`.

## Test

```powershell
python -m unittest discover tests
```

## Package Prep

Nuitka packaging prep is available after installing the package extras:

```powershell
pip install -e .[package]
.\scripts\build_phase1_nuitka.ps1
```
