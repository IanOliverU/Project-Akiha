# Phase 2 Chat Foundation

Phase 2 begins the companion layer without introducing external AI dependencies
immediately. The first slice is a chat window backed by a deterministic local
mock provider.

## Current Scope

- Chat window opened from the tray or pet right-click menu
- `AIProvider` interface
- `MockAIProvider`
- `ChatController`
- Local message history in memory
- Deterministic placeholder responses

## Not Yet In This Phase

- Ollama provider
- Streaming tokens
- qasync/QThread bridge for long-running AI requests
- SQLite conversation persistence
- memory extraction or retrieval
- personality prompt system

## Manual Smoke Test

```powershell
python -m project_akiha.app.main
```

Then check:

- Tray menu can open Chat.
- Pet right-click menu can open Chat.
- Sending a message appends `You`.
- Mock response appends `Akiha`.
- Empty messages are ignored by the UI.

