<p align="center">
  <img
    src="assets/animations/akiha/Akiha.gif"
    alt="Animated pixel-art Akiha sitting at a table"
    width="256"
  />
</p>

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
- Chat through a provider interface using local mock/Ollama modes or an
  explicitly selected hosted OpenAI-compatible service.
- Persist conversations, summaries, memories, settings, window state, and
  behavior history locally.
- Extract, validate, store, retrieve, and inject memory through a memory
  pipeline instead of a single monolithic memory service.
- React to user activity with mood-aware behavior, idle/away awareness,
  proactive check-ins, reminders, delivery guardrails, and behavior logging.
- Perform a shallow set of permission-gated desktop actions through typed
  validation, revocable grants, confirmations, and sanitized audit history.

## Current Status

Phases 1 through 7 are complete. Akiha now supports local microphone capture,
faster-whisper STT, provider-neutral TTS orchestration, local VOICEVOX playback,
automatic reply speech, and a minimal speech identity. Chat can switch between
mock, Ollama, Gemini, OpenAI, OpenRouter, Kimi, Grok, and custom
OpenAI-compatible endpoints. Hosted API keys are encrypted for the current
Windows user and never stored in ordinary TOML configuration. Phase 8 is
complete with permission-gated file discovery, approved-root and descendant
directory navigation, passive-file and local-media opening, allowlisted
application launch/close, revocable grants, confirmation surfaces, and
sanitized action history. The Python 3.13 standalone package passed automated
and manual Phase 8 verification. The optional Spotify extension is now
source-complete with PKCE account connection, permission-gated playback,
artist/track/album/playlist workflows, Liked Songs and favorite mixes, and
ephemeral local preference ranking. Its consolidated manual test and new
standalone package are deferred until the Voice Intent and Live Conversation
architecture is integrated. Pet simulation remains planned after that work.

| Phase | Status | Focus |
| --- | --- | --- |
| Phase 1 | Done | Desktop pet foundation |
| Phase 2 | Done | Chat foundation and AI provider wiring |
| Phase 3 | Done | Memory pipeline and memory management |
| Phase 4 | Done | Activity awareness, mood, proactive behavior |
| Phase 5 | Done | Companion experience polish and interaction depth |
| Phase 6 | Done | Packaging, release hardening, and maintainability |
| Phase 7 | Done | Local-first voice plumbing and Akiha voice identity |
| Phase 8 | Done | Permission-gated files and allowlisted app lifecycle actions |
| Phase 9 | Planned | Pet statistics, care actions, progression, and attention behavior |
| Phase 10 | Planned | Shop, inventory, cosmetics, and richer visual presentation |

## Tech Stack

### Runtime And App Framework

![Python](https://img.shields.io/badge/Python-3.12+-3776AB?logo=python&logoColor=white)
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
![Gemini](https://img.shields.io/badge/Gemini-optional_hosted_AI-4285F4?logo=googlegemini&logoColor=white)
![OpenAI](https://img.shields.io/badge/OpenAI-compatible_API-000000?logo=openai&logoColor=white)
![faster-whisper](https://img.shields.io/badge/faster--whisper-local_STT-2E7D32)
![Local First](https://img.shields.io/badge/Local--first-companion-2E7D32)
![Event Driven](https://img.shields.io/badge/Event--driven-core-5B5BD6)

- **MockAIProvider** keeps development deterministic and usable without a model.
- **OllamaProvider** supports optional local non-cloud chat streaming.
- **OpenAICompatibleProvider** supports hosted and self-hosted Chat Completions
  endpoints through one streaming adapter.
- **Windows DPAPI** encrypts API keys for the current Windows user separately
  from ordinary application configuration.
- **faster-whisper** provides optional local push-to-talk transcription on the
  Python 3.13 voice environment.
- **EventBus** connects UI, app controllers, memory, behavior, mood, and
  animation changes without direct cross-module coupling.
- **Provider and repository interfaces** keep AI and persistence swappable.

### Development, Quality, And Packaging

![setuptools](https://img.shields.io/badge/setuptools-packaging-4B8BBE?logo=python&logoColor=white)
![Ruff](https://img.shields.io/badge/Ruff-linting-D7FF64?logo=ruff&logoColor=black)
![Black](https://img.shields.io/badge/Black-formatting-000000?logo=python&logoColor=white)
![unittest](https://img.shields.io/badge/unittest-test_suite-336791)
![Nuitka](https://img.shields.io/badge/Nuitka-Windows_package-6A4BBC?logo=python&logoColor=white)

- **setuptools** builds and installs the package from `pyproject.toml`.
- **unittest** is the current test framework.
- **Ruff** and **Black** are used for linting and formatting.
- **Nuitka** builds the first Windows standalone package. Release-candidate
  packaging uses Python 3.13 because Python 3.14 support is still experimental
  in the current Nuitka toolchain.

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
- Optional Gemini, OpenAI, OpenRouter, Kimi, and custom compatible endpoints.
- Encrypted bring-your-own-key storage with environment-variable alternatives.
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

Details: `docs/PHASE4_ACTIVITY_MOOD_PROACTIVE.md`

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
- Phase 6 packaging checklist.

Details: `docs/PHASE5_COMPANION_POLISH.md`

### Phase 6: Packaging, Release Hardening, And Maintainability

Prepare Akiha for longer-term use and eventual distribution.

- Nuitka packaging validation for the Windows desktop app.
- Installer and release workflow preparation.
- Startup/shutdown and error recovery hardening.
- Logging, diagnostics, and supportability improvements.
- Dependency, privacy, and local-data review.
- Security checklist for future assistant capabilities.
- Final documentation pass and release notes.
- Python 3.13 standalone packaging and smoke workflow established.
- Pet-menu fallback controls for Behavior History and Quit.

Details: `docs/PHASE6_PACKAGING_RELEASE.md`

### Phase 7: Voice Layer

Give Akiha an optional local-first voice without coupling character identity to
one speech engine.

- Push-to-talk input through a local Whisper-compatible provider.
- Optional live transcription, silence endpointing, and final-transcript
  auto-send.
- Temporary Japanese speech through a local VOICEVOX provider.
- Optional background launch and owned-process shutdown for a configured
  standalone VOICEVOX Engine.
- Replaceable speech-to-text and text-to-speech provider interfaces.
- Listening, thinking, speaking, muted, and error states.
- Voice settings, diagnostics, device selection, and failure recovery.
- A minimal Akiha speech identity derived from `docs/AKIHA.MD`.
- Raw-text fallback when speech styling fails.
- Japanese canonical assistant responses with optional persisted English
  subtitles.
- A versioned first-run privacy notice for microphone and hosted processing.
- Japanese deterministic memory fallback for mock or unavailable AI providers.
- Custom voice training and cloud voice providers deferred.

Details: `docs/PHASE7_VOICE_LAYER.md`

### Phase 8: Permission-Gated Assistant Actions

Give Akiha a deliberately shallow set of safe desktop capabilities without
granting unrestricted operating-system access.

- Treat AI action proposals as untrusted structured requests.
- Validate every request through an application-owned action registry.
- Store capability- and target-specific permission grants.
- Search filenames and metadata only inside user-approved directories.
- Open approved directories and safe files through validated actions.
- Navigate ordinary child directories under an approved root using natural
  requests such as `Open Compressed inside Downloads`, without granting each
  child separately.
- Launch explicitly enabled applications such as Discord, Chrome, Spotify, and
  Visual Studio Code through a trusted application catalog.
- Gracefully close separately enabled applications such as VLC without shell
  commands or forceful process termination.
- Optionally let the selected AI provider interpret natural app-launch and
  local-media requests without disclosing filesystem paths, listings, results,
  metadata, or file contents.
- Record permission decisions and sanitized outcomes in an action audit.
- Deny shell commands, elevation, file mutation, system-critical access,
  arbitrary executables, arguments, and autonomous background actions.

Details: `docs/PHASE8_ASSISTANT_ACTIONS.md`

### Phase 9: Pet Sim Layer

Add persistent pet statistics, care actions, progression, and attention
behavior. Pet state is structured and language-neutral: dialogue reflects
stored state but never determines it through keyword or sentiment parsing.
Gameplay pressure, care-loop behavior, the minimum reaction matrix, and asset
fallbacks will be researched before implementation begins.

Details: `docs/PHASE9_PET_SIM_LAYER.md`

### Phase 10: Shop And Visual Pet Expansion

Add the visual and economic payoff after the care loop and model requirements
are proven.

- Shop and inventory.
- Currency spending.
- Buyable cosmetic items and accessories.
- Visible equipped-item state.
- Richer sprite sets or a future Live2D-compatible presentation.
- Expanded care, reward, and interaction animations.

Phase 10 remains high-level until Phase 9 research establishes the required
model and animation system.

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
- Assistant actions pass through a typed registry, validation, scoped
  permissions, capability-specific executors, and an audit repository.

## Local Data

Runtime data is stored under `%LOCALAPPDATA%\Akiha\`.

| Data | Location |
| --- | --- |
| User config | `%LOCALAPPDATA%\Akiha\user_config.toml` |
| SQLite database | `%LOCALAPPDATA%\Akiha\akiha.sqlite3` |
| Pet window state | `%LOCALAPPDATA%\Akiha\state\pet_window.json` |
| Encrypted API credentials | `%LOCALAPPDATA%\Akiha\state\credentials.json` |
| App logs | `%LOCALAPPDATA%\Akiha\logs\app.log` |
| Local voice models | `%LOCALAPPDATA%\Akiha\models\faster-whisper\` |

Details: `docs/LOCAL_DATA_PRIVACY.md`

Provider setup: `docs/AI_PROVIDERS.md`

## Run

Install the app in editable mode:

```powershell
pip install -e .[dev]
```

For optional local speech recognition, use Python 3.13:

```powershell
.\.venv313\Scripts\python.exe -m pip install -e ".[voice]"
```

Start Akiha:

```powershell
python -m project_akiha.app.main
```

To run speech without keeping the VOICEVOX editor open, open **Settings >
Voice**, enable **Start VOICEVOX automatically**, and select the standalone
VOICEVOX Engine `run.exe`. Akiha only stops an engine process that it started.

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

## Package Build

Nuitka packaging is available through the package extras. Use Python 3.13 for
release-candidate standalone builds:

```powershell
py -3.13 -m venv .venv313
.\.venv313\Scripts\python.exe -m pip install -e ".[package,voice]"
$env:PATH = (Resolve-Path '.\.venv313\Scripts').Path + ';' + $env:PATH
.\scripts\build_akiha_nuitka.ps1 -OutputDir dist\nuitka-phase8-release
```

Automated release readiness for the current standalone package:

```powershell
.\scripts\phase6_release_readiness.ps1 `
  -ExePath dist\nuitka-phase8-release\main.dist\Akiha.exe `
  -RunExistingDataPass
```

Build and release workflow details: `docs/BUILD_RELEASE.md`

Distribution decision: `docs/DISTRIBUTION_DECISION.md`

Security review: `docs/SECURITY_REVIEW.md`

Post-Phase-6 backlog: `docs/POST_PHASE6_BACKLOG.md`

Phase 8 plan: `docs/PHASE8_ASSISTANT_ACTIONS.md`

Assistant-action improvement backlog: `docs/ASSISTANT_ACTIONS_BACKLOG.md`

Spotify integration and closure record: `docs/SPOTIFY_INTEGRATION.md`

Phase 9 plan: `docs/PHASE9_PET_SIM_LAYER.md`

Manual packaged smoke checklist: `docs/MANUAL_PACKAGED_SMOKE.md`

Manual smoke report template: `docs/MANUAL_SMOKE_REPORT_TEMPLATE.md`

Release notes draft: `docs/RELEASE_NOTES_DRAFT.md`
