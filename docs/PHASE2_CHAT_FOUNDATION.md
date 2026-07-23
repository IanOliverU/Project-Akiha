# Phase 2 Chat Foundation

Phase 2 begins the companion layer without introducing external AI dependencies
immediately. The first slice is a chat window backed by a deterministic local
mock provider, with optional non-streaming Ollama support.

## Current Scope

- Chat window opened from the tray or pet right-click menu
- `AIProvider` interface
- `MockAIProvider`
- `OllamaProvider` using Ollama's local HTTP API
- `ChatController`
- QThread bridge for non-blocking chat responses
- Local message history in memory
- Deterministic placeholder responses

## Not Yet In This Phase

- streaming tokens
- qasync bridge if streaming needs tighter asyncio integration
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

## Ollama

The default provider is still `mock`, so the app works without Ollama. To use
Ollama, open Settings and set:

- AI provider: `ollama`
- Ollama URL: `http://localhost:11434`
- Ollama model: a model installed in Ollama, such as `llama3.2`

Current Ollama support uses complete non-streaming responses. Streaming token
display is a later Phase 2 refinement.
