# Post-Phase-6 Backlog

This backlog starts after Phase 6 is closed. It keeps future ideas organized so
Phase 6 can stay focused on packaging, release hardening, diagnostics, privacy,
and manual smoke validation.

## Immediate Release Follow-Up

- Review the first manual packaged smoke report.
- Decide whether the first standalone preview is ready to share.
- Rebuild the standalone package after any manual-smoke fixes.
- Preserve release notes that match the exact package being shared.
- Improve tray Show/Hide discoverability and direct tray-icon interaction
  reliability on Windows tray setups.

## Provider And API Expansion

- [x] Add a provider abstraction for multiple external model APIs.
- [x] Add presets for OpenAI, Gemini, OpenRouter, Kimi, Grok, and custom
  OpenAI-compatible chat APIs.
- [ ] Add a Claude-specific preset if direct Anthropic API support is needed.
- [x] Keep Ollama as the local/self-hosted provider option.
- [x] Add provider availability checks and clearer provider-specific diagnostics.
- [x] Add settings validation for API keys, base URLs, model names, and timeouts.
- [x] Store hosted credentials with Windows DPAPI outside ordinary TOML config.

These provider-expansion items shipped alongside Phase 7 but are parallel
post-Phase-6 backlog work, not part of the core voice-layer scope.

## Voice

- [x] Add push-to-talk or explicit voice input controls.
- [x] Add speech-to-text provider abstraction.
- [x] Add text-to-speech provider abstraction.
- [x] Add local/offline voice options where practical.
- [x] Add a versioned privacy notice for microphone and hosted processing.
- [x] Add visual states for listening, thinking, speaking, and muted modes.

## Voice Runtime Hardening

- Add a Project Akiha single-instance guard before relying on one managed local
  engine process across multiple launches.
- Decide whether the managed GPT-SoVITS API that crashes mid-session should
  restart automatically or require an explicit user retry.
- Replace short segmented Hosted Live WAV playback with a continuous PCM output
  path if V8 listening tests still expose audible seams or crackle.
- Evaluate an identity-preserving local voice backend or user-trained voice
  model behind the existing provider-neutral speech-output boundary. Keep the
  model optional and do not bundle copyrighted training material.

## Animation And Model Improvements

- Refine the current 2D Akiha sprite assets.
- Add richer idle, walk, sleep, wake, and reaction animations.
- Improve animation manifest tooling for frame sizes, offsets, and previews.
- Investigate Live2D or another advanced model backend.
- Keep the existing sprite provider as a fallback path.

## Assistant Commands And Plugins

- [x] Implement the Phase 8 assistant-action contracts and permission policy
  defined in `docs/phases/phase-08-actions/README.md`.
- [x] Keep AI output away from direct execution paths.
- [x] Add the typed action registry and validation before enabling executors.
- [x] Add user confirmation flows and scoped, revocable grants.
- [x] Add read-only file discovery inside user-approved directories.
- [x] Add allowlisted launching for explicitly enabled everyday applications.
- Explore a plugin API only after command safety boundaries are defined.

Phase 8 intentionally excludes shell commands, filesystem mutation,
administrator elevation, system-critical access, arbitrary executable paths,
OS automation, and silent background actions.

## Memory And Companion Intelligence

- Add richer long-term memory retrieval strategies.
- Revisit embeddings with an optional external or local embedding provider.
- Expand relationship modeling and emotional continuity.
- Add better memory review workflows and provenance display.
- Add backup/export options for conversations and memories.

## Distribution Polish

- Choose installer tooling after standalone-folder feedback.
- Define install location, shortcut behavior, and uninstall behavior.
- Decide whether uninstall should preserve or optionally remove local user data.
- Consider code signing before public distribution.
- Consider dependency auditing and reproducible build workflow.
- Revisit lockfile strategy for release builds.

## Out Of Scope Until This Backlog Starts

- Cloud sync.
- Autonomous desktop control.
- Silent background command execution.
- Bundling Ollama or other large model runtimes.
- Auto-update infrastructure.
