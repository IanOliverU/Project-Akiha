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

- Add a provider abstraction for multiple external model APIs.
- Add configurable providers for OpenAI, Gemini, Claude, Kimi, and other
  compatible chat APIs.
- Keep Ollama as the local/self-hosted provider option.
- Add provider availability checks and clearer provider-specific diagnostics.
- Add settings validation for API keys, base URLs, model names, and timeouts.
- Decide how provider credentials should be stored locally.

## Voice

- Add push-to-talk or explicit voice input controls.
- Add speech-to-text provider abstraction.
- Add text-to-speech provider abstraction.
- Add local/offline voice options where practical.
- Add clear privacy notices before microphone capture is introduced.
- Add visual states for listening, thinking, speaking, and muted modes.

## Animation And Model Improvements

- Refine the current 2D Akiha sprite assets.
- Add richer idle, walk, sleep, wake, and reaction animations.
- Improve animation manifest tooling for frame sizes, offsets, and previews.
- Investigate Live2D or another advanced model backend.
- Keep the existing sprite provider as a fallback path.

## Assistant Commands And Plugins

- Design explicit permission gates before any local command execution exists.
- Keep AI output away from direct execution paths.
- Add a command registry with validation before adding real commands.
- Add user confirmation flows for risky actions.
- Explore a plugin API only after command safety boundaries are defined.

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
