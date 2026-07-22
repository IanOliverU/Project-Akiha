# Project Akiha

Project Akiha is a Windows-first desktop companion app. Phase 1 focuses on the
desktop pet foundation only: a small always-on-top PySide6 window,
framework-free core state, and an internal event bus.

## Run

```powershell
python -m project_akiha.app.main
```

Install dependencies first if needed:

```powershell
pip install -e .[dev]
```

## Test

```powershell
python -m unittest discover tests
```
