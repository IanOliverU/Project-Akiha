# Assistant Actions Improvement Backlog

**Status:** Active - Spotify integration foundation in progress

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

- [x] Measure silence endpoint reliability with fan and room noise.
- [x] Add adaptive noise-floor calibration without continuous background
  recording.
- [x] Improve streaming partial transcripts and stable final-text replacement.
- [x] Prevent duplicated wrappers such as `I heard you say` from entering the
  final transcript or intent parser.
- [x] Surface microphone level, detected speech, silence countdown, and final
  transcript state without logging transcript content by default.
- [x] Add confidence-aware finalization and retain the manual Stop fallback.
- [x] Add deterministic endpoint tests for steady fan noise, speech over fan
  noise, immediate speech, muted silence, and brief noise spikes.
- [x] Add broader deterministic tests for pauses, corrections, and false
  starts as transcript stabilization is implemented.

The first endpoint-hardening pass landed on 2026-07-31. Microphone capture now
calibrates a short local noise floor after Talk begins, uses separate adaptive
speech-start and speech-release thresholds, requires sustained speech before
resetting the silence timer, and preserves a louder immediate-speech bypass.
Raw audio remains temporary and is not logged or persisted.

The physical microphone checkpoint passed on 2026-07-31 with the user's fan at
level 3, so the adaptive thresholds were retained without speculative tuning.
The next transcription pass reduced cumulative snapshot cadence from 1.0 to
0.6 seconds and added language-neutral preview stabilization. The first result
appears immediately; related growth replaces it quickly, while duplicates,
shorter regressions, and disruptive one-off rewrites are suppressed. The final
provider transcript remains authoritative. Focused coverage includes English
and Japanese growth, correction confirmation, duplicate/regression handling,
recording reset, cancellation, and final-transcript handoff.

Manual source verification confirmed the faster preview and reliable action
dispatch. Provider transcripts now pass through one conservative shared
normalizer before partial or final presentation. Repeated leading
`I heard you say` wrappers and their surrounding quotes are removed, wrapper-
only output becomes an empty-transcript failure, and the same normalization is
reused by the strict action parser. Ordinary sentences containing that phrase
away from the beginning remain unchanged.

The diagnostics and confidence pass exposes only coarse microphone states
(`calibrating`, `waiting`, `speaking`, and `pause`), level bands, and a rounded
silence countdown. Raw RMS values, audio, and transcript content never enter
the diagnostic payload. faster-whisper segment metadata is reduced to a local
bounded score and then to `low`, `medium`, or `high` before presentation. A
low-confidence final transcript is placed in the editable input for review
even when automatic sending is enabled; unknown confidence preserves existing
provider behavior. Manual Stop remains available throughout capture. Coverage
now includes short pauses, resumed speech, false starts, disruptive correction
recovery, diagnostic privacy, and confidence-gated submission.

Source QA then showed that the initial multiplicative score was too strict for
a correctly recognized two-word command. The policy was recalibrated to blend
token probability primarily with a smaller no-speech contribution and to
reserve mandatory review for clearly weak results. Deterministic cases cover a
clear short command and a genuinely uncertain high-no-speech result.

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

## Spotify Integration

- [x] Record the Premium, PKCE, fixed loopback callback, and privacy boundary.
- [x] Add typed public configuration and a Settings connection surface.
- [x] Implement PKCE authorization, callback state validation, token exchange,
  encrypted refresh-token persistence, and disconnect.
- [x] Exclude personal listening exports from Git and packaged artifacts.
- [x] Add an authenticated Spotify session with in-memory access-token refresh.
- [x] Add bounded local track, artist, album, playlist, Liked Songs, top-item,
  and recent-track lookup with minimal metadata retention.
- [ ] Add active-device selection and optional Spotify desktop-app launch.
- [ ] Add typed play, pause, resume, next, previous, and library-play actions.
- [ ] Add local preference ranking and explicit ambiguity confirmation.
- [ ] Connect constrained typed/voice proposals without exposing library data to
  hosted providers.
- [ ] Run source QA, rebuild the standalone package, and complete packaged smoke.

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
