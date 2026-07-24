# Project Akiha

Project Akiha is a Windows-first desktop companion: a small animated character
that lives on the desktop, can chat with the user, remembers durable facts with
approval-aware memory tools, and gradually becomes more context-aware through
activity, mood, and proactive behavior systems.

The project is built as a local-first companion foundation. The goal is not just
to make a chatbot with a sprite attached, but to build a reliable desktop
presence with clear architecture: UI surfaces, companion state, memory,
behavior, persistence, and future assistant capabilities stay separated enough
that the app can grow without turning into one giant service file.

## What We Are Building

Akiha is intended to become a personal desktop companion that can:

- Stay visible as a draggable, animated desktop pet.
- Offer tray, pet-menu, settings, chat, and memory-management controls.
- Chat through a provider interface, using a local mock provider by default and
  optional Ollama support when a local model is available.
- Persist conversations, summaries, memories, settings, window state, and
  behavior history locally.
- Extract, validate, store, retrieve, and inject memory through a memory
  pipeline instead of a single monolithic memory service.
- React to user activity with mood-aware behavior, idle/away awareness,
  proactive check-ins, reminders, delivery guardrails, and behavior logging.
- Grow later into a safer local assistant with explicit command validation,
  permissions, audit logs, packaging, and release hardening.

## Current Status

Phases 1 through 4 are complete. Phase 5 is the next active phase.

| Phase | Status | Focus |
| --- | --- | --- |
| Phase 1 | Done | Desktop pet foundation |
| Phase 2 | Done | Chat foundation and AI provider wiring |
| Phase 3 | Done | Memory pipeline and memory management |
| Phase 4 | Done | Activity awareness, mood, proactive behavior |
| Phase 5 | Next | Companion experience polish and interaction depth |
| Phase 6 | Planned | Packaging, release hardening, and maintainability |

## Tech Stack

### Runtime And App Framework

![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![PySide6](https://img.shields.io/badge/PySide6-Qt_6-41CD52?logo=qt&logoColor=white)
![Windows](https://img.shields.io/badge/Windows-first-0078D4?logo=windows&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-local_storage-003B57?logo=sqlite&logoColor=white)

- **Python 3.12+** is the application language.
- **PySide6 / Qt 6** powers the desktop pet, tray, settings, chat, memory, and
  delivery UI.
- **SQLite** stores conversations, messages, summaries, memories, embeddings,
  and behavior history locally.
- **TOML** is used for project metadata, default app configuration, user
  configuration, and animation manifests.

### AI And Companion Systems

![Ollama](https://img.shields.io/badge/Ollama-optional_local_AI-000000?logo=ollama&logoColor=white)
![Local First](https://img.shields.io/badge/Local--first-companion-2E7D32)
![Event Driven](https://img.shields.io/badge/Event--driven-core-5B5BD6)

- **MockAIProvider** keeps development deterministic and usable without a model.
- **OllamaProvider** supports optional local non-cloud chat streaming.
- **EventBus** connects UI, app controllers, memory, behavior, mood, and
  animation changes without direct cross-module coupling.
- **Provider and repository interfaces** keep AI and persistence swappable.

### Development, Quality, And Packaging

![setuptools](https://img.shields.io/badge/setuptools-packaging-4B8BBE?logo=python&logoColor=white)
![Ruff](https://img.shields.io/badge/Ruff-linting-D7FF64?logo=ruff&logoColor=black)
![Black](https://img.shields.io/badge/Black-formatting-000000?logo=python&logoColor=white)
![unittest](https://img.shields.io/badge/unittest-test_suite-336791)
![Nuitka](https://img.shields.io/badge/Nuitka-package_prep-6A4BBC?logo=python&logoColor=white)

- **setuptools** builds and installs the package from `pyproject.toml`.
- **unittest** is the current test framework.
- **Ruff** and **Black** are used for linting and formatting.
- **Nuitka** is prepared as the packaging path for later Windows builds.

## Roadmap Phases

### Phase 1: Desktop Pet Foundation

Build the non-AI foundation that makes Akiha feel present on the desktop.

- Transparent frameless PySide6 pet window.
- Dragging and screen-bound position persistence.
- Right-click pet menu with walking, sleeping, settings, and hide controls.
- System tray controls for show, hide, settings, chat, and quit.
- Settings window for desktop pet behavior.
- Logging under `%LOCALAPPDATA%\Akiha\logs\`.
- Sprite animation manifest loading with placeholder fallback.
- Walking animation filmstrip support and mirrored left/right walking.

Details: `docs/PHASE1_DESKTOP_PET.md`

### Phase 2: Chat Foundation

Add the first companion conversation surface while keeping model access behind a
provider interface.

- Chat window opened from tray and pet menu.
- `AIProvider` interface.
- Deterministic `MockAIProvider`.
- Optional local `OllamaProvider`.
- Streaming responses through a QThread/asyncio bridge.
- Configurable companion name and system prompt.
- SQLite conversation and message persistence.
- New chat, clear chat, export transcript, status labels, and cancellation.

Details: `docs/PHASE2_CHAT_FOUNDATION.md`

### Phase 3: Memory Pipeline

Turn raw conversations into durable, reviewable memory.

- `MemoryEntry`, `MemoryCandidate`, repository, extractor, normalizer, policy,
  and pipeline components.
- SQLite memory tables, migration runner, archiving, source references, and
  local hashing embeddings.
- Relevant memory retrieval with lexical, vector, importance, and recency
  scoring.
- Hidden memory context injection before provider calls.
- Relationship and emotional context derived from retrieved memories.
- Pending memory approval workflow.
- Memory manager UI for search, edit, archive, restore, delete, and clear.
- Closed-conversation summaries and hidden summary prompt context.

Details: `docs/PHASE3_MEMORY_LAYER.md`

### Phase 4: Activity, Mood, And Proactive Behavior

Make Akiha aware of user activity and capable of careful proactive behavior.

- Activity tracker for active, idle, and away states.
- Behavior configuration in Settings.
- Notification policy with quiet hours, cooldowns, enabled flags, and away
  guardrails.
- Proactive suggestion generation for idle check-ins and scheduled check-ins.
- Safe delivery layer for chat notices and tray messages.
- Mood model for calm, attentive, waiting, resting, checking-in, and sleepy
  states.
- Mood-to-animation mapping so behavior can influence the pet.
- Behavior event history stored in SQLite.
- Behavior history recording for proactive suggestions and delivery outcomes.

### Phase 5: Companion Experience Polish And Interaction Depth

Improve the user-facing companion experience now that the core systems exist.

- Behavior/history viewer UI.
- Better chat UX around proactive suggestions.
- User-facing behavior history cleanup controls.
- More 2D model and animation polish.
- More mood-aware visual behavior.
- Improved tray/menu controls for behavior features.
- Richer companion presence and interaction polish.
- Integration tests for the full proactive flow.
- Startup and shutdown robustness review.

### Phase 6: Packaging, Release Hardening, And Maintainability

Prepare Akiha for longer-term use and eventual distribution.

- Nuitka packaging validation for the Windows desktop app.
- Installer and release workflow preparation.
- Startup/shutdown and error recovery hardening.
- Logging, diagnostics, and supportability improvements.
- Dependency, privacy, and local-data review.
- Security checklist for future assistant capabilities.
- Final documentation pass and release notes.

## Architecture

Akiha follows a layered, event-driven structure:

```text
UI Layer (PySide6)
    -> Application Controllers
        -> Framework-free Core
            -> Providers, Repositories, Services
```

Important architectural rules:

- `core/` stays framework-free and does not import Qt.
- UI sends and receives app events instead of directly owning companion logic.
- AI access goes through provider interfaces.
- Database access goes through repository classes.
- Memory is a pipeline: extraction, normalization, validation, storage,
  retrieval, and prompt context assembly.
- Behavior is built from small components: activity, policy, proactive
  suggestions, delivery, mood, animation mapping, and history.

## Local Data

Runtime data is stored under `%LOCALAPPDATA%\Akiha\`.

| Data | Location |
| --- | --- |
| User config | `%LOCALAPPDATA%\Akiha\user_config.toml` |
| SQLite database | `%LOCALAPPDATA%\Akiha\akiha.sqlite3` |
| Pet window state | `%LOCALAPPDATA%\Akiha\state\pet_window.json` |
| App logs | `%LOCALAPPDATA%\Akiha\logs\app.log` |

## Run

Install the app in editable mode:

```powershell
pip install -e .[dev]
```

Start Akiha:

```powershell
python -m project_akiha.app.main
```

After installation, the console script is also available:

```powershell
akiha
```

## Test And Quality Checks

```powershell
python -m unittest discover tests
python -m ruff check project_akiha tests
python -m black --check project_akiha tests
python -m compileall project_akiha tests
```

## Package Prep

Nuitka packaging prep is available through the package extras:

```powershell
pip install -e .[package]
.\scripts\build_phase1_nuitka.ps1
```

Packaging is not the active project phase yet; it remains part of Phase 6.
