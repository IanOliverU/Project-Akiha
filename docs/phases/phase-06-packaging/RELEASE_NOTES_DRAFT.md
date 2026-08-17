# Release Notes Draft

These notes describe the Phase 8 Project Akiha standalone Windows preview after
automated and manual assistant-action validation.

## Project Akiha 0.1.0 Standalone Preview

Project Akiha is a Windows-first desktop companion with a draggable 2D pet,
provider-neutral chat, local memory, activity-aware mood behavior, proactive
check-ins, optional local voice, and diagnostics.

## Included

- Transparent desktop pet window with draggable position.
- Right-click pet controls and system tray controls.
- Settings window for pet, AI, memory, behavior, and voice options.
- Chat window with streaming responses, cancellation, new chat, clear chat, and
  transcript export.
- Mock AI provider for offline deterministic use and optional local Ollama.
- Explicitly selected Gemini, OpenAI, OpenRouter, Kimi, Grok, and custom
  OpenAI-compatible providers.
- Windows-user encrypted storage for hosted API credentials.
- SQLite persistence for conversations, messages, summaries, memories,
  embeddings, and behavior history.
- Memory Manager for active, archived, and pending memories.
- Behavior History viewer and cleanup controls.
- Activity, mood, proactive suggestion, scheduled check-in, and delivery
  guardrail systems.
- Local diagnostics: logs, startup diagnostics summary, and Settings actions to
  open logs/data folders.
- Local push-to-talk transcription through faster-whisper.
- Local Japanese synthesis through GPT-SoVITS with optional managed API
  startup and owned-process shutdown.
- Live transcription, silence endpointing, final-transcript auto-send,
  automatic reply speech, stop, and replay controls.
- Canonical Japanese assistant replies with optional persisted English
  subtitles.
- Versioned first-run privacy notice for microphone and hosted processing.
- English and Japanese deterministic memory fallback.
- Permission-gated file search inside user-approved directories.
- Approved-root and descendant-directory navigation without unrestricted
  filesystem access or persistent full-tree indexing.
- Confirmed passive-file and local-media opening through the system handler.
- Allowlisted Chrome, Discord, Spotify, VLC, and Visual Studio Code launch and
  graceful-close actions with separate revocable permissions.
- Optional constrained AI intent proposals that never receive local paths,
  directory listings, search results, metadata, or file contents from Akiha.
- Sanitized assistant-action history, diagnostics, and permission management.

## Packaging

- First package format: standalone folder.
- Current candidate package:
  `dist\nuitka-v5-local-voice-final\main.dist\Akiha.exe`
- Release-candidate packaging uses Python 3.13.14 with Nuitka 4.1.3.
- Automated source smoke, packaged smoke, and manual packaged smoke passed on
  the current candidate package.
- Installer: not included in the first standalone preview.
- Local data path: `%LOCALAPPDATA%\Akiha\`
- Build workflow: `docs/phases/phase-06-packaging/BUILD_RELEASE.md`
- Distribution decision: `docs/phases/phase-06-packaging/DISTRIBUTION_DECISION.md`
- Local data and privacy: `docs/reference/LOCAL_DATA_PRIVACY.md`
- Security review: `docs/reference/SECURITY_REVIEW.md`
- General future backlog: `docs/roadmap/PROJECT_BACKLOG.md`
- Assistant-action improvements: `docs/phases/phase-08-actions/BACKLOG.md`
- Manual packaged smoke:
  `docs/phases/phase-06-packaging/MANUAL_PACKAGED_SMOKE.md`
- Manual smoke report template:
  `docs/phases/phase-06-packaging/MANUAL_SMOKE_REPORT_TEMPLATE.md`

## Source-Complete After Current Candidate

The source tree now also contains the source-complete Spotify implementation:

- Authorization Code with PKCE and DPAPI-encrypted refresh-token storage.
- Separate revocable Spotify playback permission and sanitized action audit.
- Play, pause, resume, next, previous, shuffle, repeat, volume, and seek.
- Artist, track, album, and playlist search, selection, opening, and playback.
- Liked Songs and bounded favorites-mix playback.
- Memory-only local preference ranking with explicit ambiguity choices.

These additions passed the 2026-08-01 automated baseline of 927 tests with 3
skipped. They are not represented by the existing Phase 8 package named above.
Spotify now has an independent manual roundup and replacement-package release
gate. It no longer waits for Voice Intent and Live Conversation integration.

## Known Limitations

- The non-interactive smoke script may force-stop the app after requesting
  `CloseMainWindow()`. Manual pet-menu Quit was validated separately.
- Direct tray Show/Hide interaction may need additional polish on some Windows
  tray setups. The pet right-click menu provides fallback access to critical
  controls, including Behavior History and Quit.
- Ollama is not bundled.
- faster-whisper models and GPT-SoVITS are separately installed local
  dependencies.
- Hosted providers require the user's own API key and may impose quotas or
  charges.
- The Akiha GPT-SoVITS reference voice is local project data and custom voice
  training remains outside this release.
- There is no always-listening wake word or background microphone capture.
- The 2D model and animation assets are functional but still planned for later
  refinement.
- No installer, shortcuts, auto-start, updater, or code signing are included in
  the first standalone preview.
- The current packaged candidate predates the source-complete Spotify
  integration; use the source application for Spotify testing until the next
  integrated rebuild.

## Manual Smoke Checklist Before Finalizing

The latest manual smoke report is in `dist\manual-smoke-reports\`.
