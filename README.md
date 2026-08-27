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

Phases 1 through 8 are complete. Akiha now supports local microphone capture,
faster-whisper STT, provider-neutral TTS orchestration, local GPT-SoVITS playback,
automatic reply speech, and a minimal speech identity. Chat can switch between
mock, Ollama, Gemini, OpenAI, OpenRouter, Kimi, Grok, and custom
OpenAI-compatible endpoints. Hosted API keys are encrypted for the current
Windows user and never stored in ordinary TOML configuration. Phase 8 is
complete with permission-gated file discovery, approved-root and descendant
directory navigation, passive-file and local-media opening, allowlisted
application launch/close, revocable grants, confirmation surfaces, and
sanitized action history. The optional Spotify extension provides PKCE account
connection, permission-gated playback,
artist/track/album/playlist workflows, Liked Songs and favorite mixes, and
ephemeral local preference ranking. Post-Phase 8 Voice Intelligence milestones
V0 through V5 are complete: Akiha now owns a provider-neutral, pipelined local
voice coordinator with rolling recognition, contextual intent correction,
streamed GPT-SoVITS speech, interruption, and bounded multi-turn Conversation
Sessions. The final Python 3.13 V5 standalone passed automated fresh/existing
data smoke checks and the complete manual voice, provider, conversation,
context, action, and shutdown checklist. V6 is complete: V6A established
the provider-neutral hosted-live contracts, V6B added the optional concrete
Gemini SDK and bounded native-audio transport, V6C added ordered live transcript
projection with final-only canonical persistence, and V6D added provider-native
barge-in with immediate local playback cancellation and stale-output rejection.
V6E now adds explicit hosted-session ownership, a hard logical deadline,
memory-only resumption handles, `GoAway` handling, and bounded reconnects that
cannot extend the session. V6F adds separate cloud-audio consent, hosted model,
native voice, duration, and local-only readiness diagnostics. V6G now wires the
explicit Local/Cloud runtime selector, direct Gemini microphone streaming,
canonical final transcript persistence, native playback, visible lane state,
provider-native barge-in, and fail-closed behavior with no silent local or cloud
fallback. These additions do not weaken or replace the complete local modular
lane. V6H completed fake-protocol and real Gemini verification, including
continuous multi-turn conversation and automatic return to listening. Native
audio crackle remains release-quality follow-up work, while final hosted-live
packaging remains intentionally deferred to V8. V7A now adds an explicit
provider-facing tool-schema catalog that exposes only separately opted-in
Phase 8 actions and never grants execution authority. V7B now adds session- and
turn-owned conversion from a ready provider proposal into one untrusted Phase
8 request, with stale, duplicate, ambiguous, and unexposed proposals rejected
before validation. V7C now routes accepted proposals through the existing
permission, confirmation, execution, and audit boundary and returns only
generic provider-safe results. V7D now declares the explicit action catalog to
Gemini Live, translates SDK function calls into untrusted proposals, pauses
confirmation-required calls for a trusted local dialog, and returns only
ID-matched sanitized results. V7E now gives compatible Ollama models the same
native proposal path through an ephemeral local turn authority, while keeping
permission checks, confirmations, execution, and audit entirely application
owned. V7F now mechanically preserves deterministic-first routing and permits
only one constrained JSON fallback callback for an owned turn, with compound
desktop requests clarified locally. V7G now closes the provider-tool
milestone: automated verification passes across the shared Gemini/Ollama
permission, execution, sanitization, replay, and audit boundary, and the real
Gemini Live source roundup passed application, Spotify, approved-directory,
local-media, result-selection, and continued-conversation checks. Packaged
hosted-live verification is now closed by the final V8 standalone. The package
passed fresh/existing-data automation and real-device microphone, Gemini Live,
provider-tool, Spotify, transcript, and graceful-shutdown checks. Pet
simulation remains planned after the completed Voice Intelligence roadmap.

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
| Post-Phase 8 V0-V5 | Done | Modular pipelined voice intelligence and local conversation |
| Post-Phase 8 V6-V8 | Done | Gemini Live, provider tools, and final standalone release verification |
| Phase 9 | Done | Pet statistics, care actions, progression, and attention behavior |
| Phase 10 | Done | Shop, fixed appearances, and autonomous pet activity |
| Phase 11 | In progress | Read-only Gmail and officially supported Discord awareness; shared privacy-safe foundation complete |

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
- **Google Gen AI SDK** is an optional, lazily loaded transport for Gemini Live;
  its SDK objects remain behind Akiha's provider-neutral voice contracts.
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

Details: `docs/phases/phase-01-desktop-pet/README.md`

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

Details: `docs/phases/phase-02-chat/README.md`

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

Details: `docs/phases/phase-03-memory/README.md`

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

Details: `docs/phases/phase-04-behavior/README.md`

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

Details: `docs/phases/phase-05-polish/README.md`

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

Details: `docs/phases/phase-06-packaging/README.md`

### Phase 7: Voice Layer

Give Akiha an optional local-first voice without coupling character identity to
one speech engine.

- Push-to-talk input through a local Whisper-compatible provider.
- Optional live transcription, silence endpointing, and final-transcript
  auto-send.
- Japanese speech through the local GPT-SoVITS Akiha voice provider.
- Optional background launch and owned-process shutdown for the managed
  GPT-SoVITS API.
- Replaceable speech-to-text and text-to-speech provider interfaces.
- Listening, thinking, speaking, muted, and error states.
- Voice settings, diagnostics, device selection, and failure recovery.
- A minimal Akiha speech identity derived from `docs/reference/AKIHA.md`.
- Raw-text fallback when speech styling fails.
- Japanese canonical assistant responses with optional persisted English
  subtitles.
- A versioned first-run privacy notice for microphone and hosted processing.
- Japanese deterministic memory fallback for mock or unavailable AI providers.
- Custom voice training and cloud voice providers deferred.

Details: `docs/phases/phase-07-voice/README.md`

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

Details: `docs/phases/phase-08-actions/README.md`

### Phase 9: Pet Sim Layer

Add persistent pet statistics, care actions, progression, and attention
behavior. Pet state is structured and language-neutral: dialogue reflects
stored state but never determines it through keyword or sentiment parsing.
Phase 9A approved the gameplay pressure, care-loop behavior, reaction matrix,
asset contract, and fallback policy. Phase 9B adds immutable pet-state models,
validated invariants, typed interaction inputs, partial decay progress, and
pure clock-independent elapsed-time rules. Phase 9C adds migration `0009`, a
revisioned SQLite repository, atomic typed history, bounded startup catch-up,
and the sole injected-clock pet-state service mutation boundary. Phase 9D adds
pure typed care actions, durable floor recovery, capped no-op handling, and
specific care history records. Phase 9E adds restart-safe reward history,
typed conversation-event rewards, XP-derived levels, currency accrual,
cooldowns, rolling daily caps, and duplicate-event protection. Phase 9F adds a
compact `Akiha Care` window with persisted need bars, level and currency
progress, and typed Feed, Rest, and Spend time controls available from the pet
and tray menus. Phase 9G settles runtime decay once per minute off the Qt UI
thread, emits only typed need-band transitions, maps the selected transition to
mood, and routes at most one edge-triggered check-in through the existing
quiet-hours, away-state, and cooldown policy. The active idle loop references
only the authoritative standing sprite and applies restrained integer-pixel
motion; nearest-neighbor rendering preserves its original hard pixel edges.
Phase 9H publishes sanitized care, affection, and level events only from
committed typed outcomes, then routes bounded local voice lines and safe
sleep/idle fallbacks through the existing voice, mood, animation, proactive,
and behavior-history systems. Phase 9I adds read-only pet diagnostics and a
confirmed, atomic reset operation that restores only pet state and progression
while preserving chat, memories, settings, permissions, Spotify data, and
general behavior history. The reset remains unavailable to AI providers and
assistant-action tools. Phase 9J passes the full automated source gate. Owner
source acceptance and real Gemini/GPT-SoVITS runtime smoke passed on 2026-08-20.
One corrected standalone, real packaged provider smoke, and final visual, voice,
interaction, and graceful-Quit approval are consolidated into the post-Phase 10
release gate so Phase 10 feature work is not blocked by repeated multi-hour builds.

Details: `docs/phases/phase-09-pet-sim/README.md`

### Phase 10: Shop, Appearance, And Autonomous Pet Expansion

Add a lightweight visual and economic payoff after the care loop without
turning Akiha into a wardrobe manager or demanding virtual-pet game.

- Trusted optional shop, durable ownership, and atomic currency spending.
- Three complete canonical appearances: Seifuku, Dress, and Vermillion.
- Simple whole-appearance selection with no clothing slots or layered cosmetics.
- An Akiha-specific Status surface built from useful existing state.
- Data-driven autonomous activities controlled by pet behavior rather than an
  LLM.
- Expanded reactions only when owner-approved sprite assets exist.

Phase 10 is specified in `docs/phases/phase-10-shop-visual/README.md`. Phases
10A-10J provide the economy, trusted catalog, persistence, Shop/Appearance
UI, whole-manifest selection, fingerprinted owner approvals, production-
renderer preview validation, and deterministic autonomous idle/wander/rest
behavior. The activity controller uses typed local state and remains
independent from dialogue and AI providers. The canonical Akiha sprite remains
immutable; Dress and Vermillion stay unavailable until their complete asset
sets pass validation and owner visual approval. Phase 10 formally closed on
2026-08-24 after source and packaged owner acceptance. The scheduled
consolidated FastBuild completed the same day and now includes the accumulated
speech-batching and GPT-SoVITS synthesis-normalization improvements in the
accepted `dist/nuitka-development/main.dist` candidate.

## Architecture

Akiha follows a layered, event-driven structure:

```text
UI Layer (PySide6)
    -> Application Controllers
        -> Framework-free Core
            -> Providers, Integrations, Repositories, Services
```

Important architectural rules:

- `core/` stays framework-free and does not import Qt.
- UI sends and receives app events instead of directly owning companion logic.
- AI access goes through provider interfaces.
- Database access goes through repository classes.
- External product integrations live under `project_akiha/integrations/` and
  still enter the app through typed service and permission boundaries.
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

Details: `docs/reference/LOCAL_DATA_PRIVACY.md`

Provider setup: `docs/reference/AI_PROVIDERS.md`

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

To run speech, open **Settings > Voice**, select **GPT-SoVITS**, and enable
automatic local TTS startup. Project Akiha starts and stops its managed
GPT-SoVITS API process without requiring a third-party desktop application.

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

Packaging tools are available through the package extras and require Python
3.13. PyInstaller one-folder is the fast development loop; it preserves the
same artifact/privacy validation without compiling the dependency graph to C:

```powershell
py -3.13 -m venv .venv313
.\.venv313\Scripts\python.exe -m pip install -e ".[package,voice,live]"
.\scripts\build_akiha_pyinstaller.ps1
```

The candidate is written to `dist\pyinstaller-development\Akiha`. Its first
Phase 10 build completed in about 2 minutes 35 seconds, and an unchanged cached
rebuild completed in about 12 seconds on the development machine. PyInstaller
is intentionally one-folder/windowed; it is not the public release format.

Nuitka remains the release-candidate path. Cached development candidates are
used to verify packaged behavior without repeating a clean multi-hour compile:

```powershell
$env:PATH = (Resolve-Path '.\.venv313\Scripts').Path + ';' + $env:PATH
.\scripts\build_akiha_nuitka.ps1 `
  -FastBuild `
  -RequireBuildReuse
```

Use a clean build only when closing a phase or preparing a release candidate:

```powershell
.\scripts\build_akiha_nuitka.ps1 `
  -CleanRelease `
  -OutputDir dist\nuitka-release
```

Development and release builds use separate Nuitka caches. Every invocation
records stage timings under the output directory's `build-reports` folder, and
packaged builds also create a Nuitka XML compilation report.
FastBuild uses the persistent `dist\nuitka-development` workspace with 10 jobs,
managed Zig 0.16.0, LTO disabled, and the unsafe Nuitka bytecode cache disabled.
It retains the expensive C-object cache and pins Zig's native caches beneath
`dist\build-cache\nuitka-dev`; reserve CleanRelease for phase closure and
release verification.

Automated release readiness for the current standalone package:

```powershell
.\scripts\phase6_release_readiness.ps1 `
  -ExePath dist\nuitka-v8-final\main.dist\Akiha.exe `
  -RunExistingDataPass
```

Documentation index: `docs/README.md`

Build and release workflow details:
`docs/phases/phase-06-packaging/BUILD_RELEASE.md`

Distribution decision: `docs/phases/phase-06-packaging/DISTRIBUTION_DECISION.md`

Security review: `docs/reference/SECURITY_REVIEW.md`

Project backlog: `docs/roadmap/PROJECT_BACKLOG.md`

Phase 8 plan: `docs/phases/phase-08-actions/README.md`

Assistant-action improvement backlog: `docs/phases/phase-08-actions/BACKLOG.md`

Spotify integration and closure record:
`docs/phases/phase-08-actions/SPOTIFY_INTEGRATION.md`

Post-Phase 8 Voice Intelligence V0-V8 architecture and evidence:
`docs/roadmap/VOICE_INTELLIGENCE_V0_V8.md`

Phase 9 plan: `docs/phases/phase-09-pet-sim/README.md`

Manual packaged smoke checklist:
`docs/phases/phase-06-packaging/MANUAL_PACKAGED_SMOKE.md`

Manual smoke report template:
`docs/phases/phase-06-packaging/MANUAL_SMOKE_REPORT_TEMPLATE.md`

Final V8 manual smoke report:
`docs/phases/phase-06-packaging/V8_MANUAL_SMOKE_2026-08-13.md`

Release notes draft: `docs/phases/phase-06-packaging/RELEASE_NOTES_DRAFT.md`
