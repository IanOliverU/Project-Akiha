# ARCHITECTURE.md — Project Akiha

Quick-reference architecture doc. For full rationale and the original analysis, see the project's architecture brief; this file is the condensed version meant to be re-read at the start of any session that touches structure.

## Layers

```
UI Layer (PySide6)  →  Application Core (framework-free)  →  Adapters (Ollama, SQLite, TTS, Automation)
```

- **UI Layer**: pet window, chat window, settings window, animation renderer. Talks to Core only via Qt signals bridged to the EventBus.
- **Application Core**: EventBus, StateManager, PersonalityEngine, MemoryService, AssistantService, PluginManager. No Qt or Ollama imports. Depends only on interfaces.
- **Adapters**: implementations of Core's interfaces — `OllamaProvider`, `SQLiteMemoryRepository`, `PiperTTSAdapter`, `AutomationBackend`.

## Folder structure

```
project_akiha/
├── app/                 # Entry point, DI wiring
├── core/                # Framework-free logic — events, state, personality, interfaces
├── ai/                  # Providers (Ollama etc.) + prompt templates
├── memory/              # MemoryRepository + models + summarizer
├── database/             # Connection + migrations/ (versioned)
├── automation/           # Command objects + PermissionGate
├── ui/                    # pet_window, chat_window, settings_window, animations
├── plugins/               # Plugin API/manifest schema + loader
├── config/                # pydantic schema + defaults.toml
├── services/              # Logging, notifications, cross-cutting concerns
├── assets/
└── tests/
    ├── unit/
    └── integration/
```

## Core interfaces (define before implementing)

```python
class AIProvider(ABC):
    async def stream_response(self, messages, system_prompt) -> AsyncIterator[str]: ...
    async def is_available(self) -> bool: ...

class MemoryRepository(ABC):
    async def save_message(self, message: Message) -> None: ...
    async def get_recent(self, n: int) -> list[Message]: ...
    async def save_memory(self, memory: MemoryEntry) -> None: ...
    async def retrieve_relevant(self, query: str, limit: int) -> list[MemoryEntry]: ...

class TTSProvider(ABC):
    async def synthesize(self, text: str) -> bytes: ...

class AutomationBackend(ABC):
    async def execute(self, command: "Command") -> "CommandResult": ...
```

## Event bus — event types

Define in `core/events/types.py` as constants/enum, not raw strings scattered around:

`mood_changed`, `message_received`, `message_sent`, `idle_detected`, `state_changed` (animation), `reminder_due`, `command_requested`, `command_executed`, `plugin_loaded`, `error_occurred`.

## State machines

- **AnimationState**: `idle`, `walking`, `dragging`, `sleeping`, (future: expression states)
- **MoodState**: driven by `PersonalityEngine`, independent axis from animation state — don't conflate them.

## Database

Tables: `conversations`, `messages`, `memories`, `personality_state`, `reminders`, `user_preferences`, `plugin_data`. All schema changes via `database/migrations/NNNN_description.sql` with a tracked `schema_version`.

## Memory tiers

1. Working memory (current session, in-context)
2. Episodic (full logs in SQLite, retention-windowed)
3. Long-term (summarized `memories` entries with importance score — this is what's retrieved for prompts, not raw logs)

No vector DB until keyword/recency/importance SQL retrieval actually proves insufficient.

## Automation / Command pattern

```python
class Command(ABC):
    required_permission: Permission
    async def execute(self) -> CommandResult: ...
    async def undo(self) -> None: ...  # where meaningful
```

All commands — whether triggered by user input or AI output — pass through `PermissionGate.check(command)` before `execute()`. Every execution is logged to an audit table.

## Plugin architecture

- Manifest (`manifest.toml`): name, version, requested permissions, entry point.
- `PluginContext` injected into plugins: scoped EventBus access + explicitly allowed services only.
- In-process Python plugins are NOT a real security boundary — document this. Real sandboxing (subprocess + IPC) is required before accepting third-party plugins.

## Packaging

Nuitka (preferred over PyInstaller — fewer AV false positives), code signing before public release, Inno Setup installer. See `SECURITY.md` for the full rationale.

## The five things that are expensive to change later

1. `core/` stays framework-free.
2. `AIProvider` interface exists before the first Ollama call.
3. Migrations exist before the first schema change.
4. EventBus is the only inter-module channel.
5. Command + PermissionGate exists before Phase 5 (Local Assistant).
