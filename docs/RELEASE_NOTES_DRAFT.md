# Release Notes Draft

These notes are a draft for the first Project Akiha standalone Windows package.
Do not treat them as final until the remaining Phase 6 manual smoke checks pass.

## Project Akiha 0.1.0 Standalone Preview

Project Akiha is a Windows-first local desktop companion with a draggable 2D pet,
chat, local memory, activity-aware mood behavior, proactive check-ins, and
diagnostics.

## Included

- Transparent desktop pet window with draggable position.
- Right-click pet controls and system tray controls.
- Settings window for pet, AI, memory, and behavior options.
- Chat window with streaming responses, cancellation, new chat, clear chat, and
  transcript export.
- Mock AI provider for offline deterministic use.
- Optional Ollama HTTP provider when Ollama is installed separately.
- SQLite persistence for conversations, messages, summaries, memories,
  embeddings, and behavior history.
- Memory Manager for active, archived, and pending memories.
- Behavior History viewer and cleanup controls.
- Activity, mood, proactive suggestion, scheduled check-in, and delivery
  guardrail systems.
- Local diagnostics: logs, startup diagnostics summary, and Settings actions to
  open logs/data folders.

## Packaging

- First package format: standalone folder.
- Current candidate package:
  `dist\nuitka-phase6-py313\main.dist\Akiha.exe`
- Release-candidate packaging uses Python 3.13.14 with Nuitka 4.1.3.
- Automated source and packaged smoke passed on the current candidate package.
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

- Manual packaged UI smoke testing is still required before final release.
- The non-interactive smoke script may force-stop the app after requesting
  `CloseMainWindow()`. Tray Quit still needs manual validation.
- The first package does not include cloud AI providers.
- Voice input and voice output are not implemented yet.
- Ollama is not bundled.
- The 2D model and animation assets are functional but still planned for later
  refinement.
- No installer, shortcuts, auto-start, updater, or code signing are included in
  the first standalone preview.

## Manual Smoke Checklist Before Finalizing

Use `docs/MANUAL_PACKAGED_SMOKE.md` before finalizing the standalone preview.
