# Phase 2 Chat Foundation

Phase 2 begins the companion layer without introducing external AI dependencies
immediately. The first slice is a chat window backed by a deterministic local
mock provider, with optional Ollama support and a configurable personality
prompt.

## Current Scope

- Chat window opened from the tray or pet right-click menu
- `AIProvider` interface
- `MockAIProvider`
- `OllamaProvider` using Ollama's local HTTP API
- `ChatController`
- QThread bridge for non-blocking chat responses
- Streaming response chunks into the chat window
- Local message history in memory
- Deterministic placeholder responses
- Configurable companion name and system prompt
- System prompt injection through `ChatController` before provider calls

## Not Yet In This Phase

- richer token-level styling and cancellation controls
- qasync bridge if model integration needs tighter asyncio integration
- SQLite conversation persistence
- memory extraction or retrieval

## Manual Smoke Test

```powershell
python -m project_akiha.app.main
```

Then check:

- Tray menu can open Chat.
- Pet right-click menu can open Chat.
- Sending a message appends `You`.
- Mock response appends the configured companion name.
- Empty messages are ignored by the UI.

## Ollama

The default provider is still `mock`, so the app works without Ollama. To use
Ollama, open Settings and set:

- AI provider: `ollama`
- Ollama URL: `http://localhost:11434`
- Ollama model: a model installed in Ollama, such as `llama3.2`

Current Ollama support streams response chunks into the chat window.

## Personality

Open Settings to edit:

- Companion name
- System prompt

The prompt may include `{character_name}`, which is replaced before the message
history is sent to the active provider. The system prompt is not stored in the
visible chat history.
