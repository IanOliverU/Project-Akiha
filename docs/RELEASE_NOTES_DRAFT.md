# Release Notes Draft

These notes describe the Phase 7 Project Akiha standalone Windows preview after
automated and manual voice validation.

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
- Local Japanese synthesis through VOICEVOX with optional managed engine
  startup and owned-process shutdown.
- Live transcription, silence endpointing, final-transcript auto-send,
  automatic reply speech, stop, and replay controls.
- Canonical Japanese assistant replies with optional persisted English
  subtitles.
- Versioned first-run privacy notice for microphone and hosted processing.
- English and Japanese deterministic memory fallback.

## Packaging

- First package format: standalone folder.
- Current candidate package:
  `dist\nuitka-phase7-final-voice\main.dist\Akiha.exe`
- Release-candidate packaging uses Python 3.13.14 with Nuitka 4.1.3.
- Automated source smoke, packaged smoke, and manual packaged smoke passed on
  the current candidate package.
- Installer: not included in the first standalone preview.
- Local data path: `%LOCALAPPDATA%\Akiha\`
- Build workflow: `docs/BUILD_RELEASE.md`
- Distribution decision: `docs/DISTRIBUTION_DECISION.md`
- Local data and privacy: `docs/LOCAL_DATA_PRIVACY.md`
- Security review: `docs/SECURITY_REVIEW.md`
- Future backlog: `docs/POST_PHASE6_BACKLOG.md`
- Manual packaged smoke: `docs/MANUAL_PACKAGED_SMOKE.md`
- Manual smoke report template: `docs/MANUAL_SMOKE_REPORT_TEMPLATE.md`

## Known Limitations

- The non-interactive smoke script may force-stop the app after requesting
  `CloseMainWindow()`. Manual pet-menu Quit was validated separately.
- Direct tray Show/Hide interaction may need additional polish on some Windows
  tray setups. The pet right-click menu provides fallback access to critical
  controls, including Behavior History and Quit.
- Ollama is not bundled.
- faster-whisper models and VOICEVOX are separately installed local
  dependencies.
- Hosted providers require the user's own API key and may impose quotas or
  charges.
- The Japanese VOICEVOX speaker is temporary; custom voice training is deferred.
- There is no always-listening wake word or background microphone capture.
- The 2D model and animation assets are functional but still planned for later
  refinement.
- No installer, shortcuts, auto-start, updater, or code signing are included in
  the first standalone preview.

## Manual Smoke Checklist Before Finalizing

The latest manual smoke report is in `dist\manual-smoke-reports\`.
