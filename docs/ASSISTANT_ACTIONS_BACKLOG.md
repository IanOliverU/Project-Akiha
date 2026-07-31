# Assistant Actions Improvement Backlog

**Status:** Planned - post-Phase-8 maintenance and refinement

## Purpose

Phase 8 established the permission-gated action boundary and is closed. This
document tracks incremental improvements that make spoken and typed actions
feel more conversational without weakening that boundary or turning them into
a new implementation phase.

The guiding pipeline is:

```text
microphone -> speech endpointing -> transcript stabilization
           -> intent proposal -> context resolution
           -> typed action request -> validation and permission
           -> confirmation when needed -> execution -> sanitized audit
```

Every provider response and transcript remains untrusted input. Only registered
typed actions may reach an executor.

## Hearing And Transcription

- [ ] Measure silence endpoint reliability with fan and room noise.
- [x] Add adaptive noise-floor calibration without continuous background
  recording.
- [ ] Improve streaming partial transcripts and stable final-text replacement.
- [ ] Prevent duplicated wrappers such as `I heard you say` from entering the
  final transcript or intent parser.
- [ ] Surface microphone level, detected speech, silence countdown, and final
  transcript state without logging transcript content by default.
- [ ] Add confidence-aware finalization and retain the manual Stop fallback.
- [x] Add deterministic endpoint tests for steady fan noise, speech over fan
  noise, immediate speech, muted silence, and brief noise spikes.
- [ ] Add broader deterministic tests for pauses, corrections, and false
  starts as transcript stabilization is implemented.

The first endpoint-hardening pass landed on 2026-07-31. Microphone capture now
calibrates a short local noise floor after Talk begins, uses separate adaptive
speech-start and speech-release thresholds, requires sustained speech before
resetting the silence timer, and preserves a louder immediate-speech bypass.
Raw audio remains temporary and is not logged or persisted.

## Intent And Context

- [ ] Keep deterministic local parsing as the fast offline path for explicit
  commands.
- [ ] Let an optional LLM produce only strict structured proposals for freer
  conversational phrasing.
- [ ] Add confidence and ambiguity results instead of guessing a target.
- [ ] Expand temporary context for references such as `inside it`, `that
  folder`, `close it`, and `play the first one`.
- [ ] Track recent opaque result identifiers without exposing paths to hosted
  providers.
- [ ] Improve alias normalization for application names, directory names,
  artists, titles, and common transcription mistakes.
- [ ] Ask a concise confirmation when multiple approved targets remain viable.

## Action Experience

- [ ] Improve spoken feedback for success, denial, unavailable targets, and
  confirmation prompts.
- [ ] Add graceful already-open and already-closed application outcomes.
- [ ] Improve relative directory navigation while retaining approved-root
  containment checks.
- [ ] Improve file and media ranking using local filename metadata only.
- [ ] Keep cancellation responsive across transcription, proposal, search, and
  execution workers.
- [ ] Add an end-to-end diagnostic view for hearing, intent, permission, and
  execution stages using sanitized data.

## Hard Safety Rules

- No arbitrary shell, PowerShell, command-line, or administrator execution.
- No unrestricted filesystem access or access outside approved roots.
- No local path, directory listing, search result, metadata, or file content is
  appended to hosted-provider prompts by Akiha.
- No provider receives an executor, filesystem repository, subprocess handle,
  or permission-service reference.
- No silent background actions, persistent microphone capture, or wake word.
- Ambiguous or higher-consequence actions fail closed or require confirmation.

## Completion Evidence

Each implemented improvement should include focused automated tests, an update
to the relevant privacy/security documentation when its data boundary changes,
and source plus packaged smoke verification when packaged behavior is affected.
