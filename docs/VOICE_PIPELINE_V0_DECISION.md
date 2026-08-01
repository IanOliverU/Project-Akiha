# Voice Pipeline V0 Decision

**Status:** Accepted

**Decision date:** 2026-08-01

**Decision:** Retain Akiha-owned orchestration. Do not add Pipecat as a
production, development, or packaging dependency.

## Context

Post-Phase 8 requires a concurrent voice pipeline that supports progressive
transcription, local and hosted text providers, ordered VOICEVOX speech,
interruption, typed assistant actions, and eventual hosted live-audio modes.
Milestone V0 evaluated whether Pipecat should own that orchestration.

Pipecat 1.6.0 was technically capable of passing text and termination frames on
Python 3.13 and Windows. The V0 bridges also proved that Akiha's existing
services can implement the required boundaries directly:

- the existing Qt microphone remains the only capture owner
- rolling revisions preserve one authoritative final transcript
- local and hosted text providers share one response contract
- VOICEVOX segments synthesize concurrently and play in canonical order
- the existing Qt playback object remains the only output owner
- action proposals still cross Akiha's validator, permissions, executor
  registry, and audit boundary
- one turn identity cancels capture, recognition, proposals, synthesis, and
  playback and rejects late callbacks

## Evidence

The isolated Pipecat environment occupied roughly 564-600 MB before freezing.
The minimal text-only Nuitka probe selected 2,938 modules, exceeded 20 minutes,
produced 2,733,437,981 bytes of incomplete standalone output, and never created
a runnable executable. Source startup also attempted an unnecessary online
NLTK `punkt_tab` lookup.

By comparison, the existing full Phase 8 Akiha standalone folder is about 329
MB and already packages Qt, voice, memory, actions, Spotify, and application
UI. Full Pipecat adoption would therefore work against the project's local,
responsive, and storage-conscious goals without providing a capability that V0
failed to reproduce through existing Akiha services.

Full measurements are recorded in `docs/VOICE_PIPELINE_V0_EVALUATION.md`.

## Consequences

- V1 implements `VoiceSessionCoordinator` as an Akiha-owned service.
- Production contracts remain framework-neutral and provider-neutral.
- Pipecat frame classes, workers, events, and provider types do not enter
  `project_akiha`.
- Both local LLMs and hosted text APIs continue through Akiha's existing
  provider interfaces.
- Future Gemini Live or other realtime adapters translate provider-native
  events at the adapter boundary; they do not replace the canonical session,
  memory, identity, subtitle, permission, or audit pipelines.
- The V0 spike remains non-packaged reference and test evidence. It is not a
  runtime dependency.

## Reconsideration

Revisit this decision only if a future orchestration framework demonstrates all
of the following in a fresh bounded spike:

- a meaningfully smaller optional core dependency graph
- offline startup without implicit model or language-data downloads
- a successful Python 3.13 Windows Nuitka build within an agreed time and size
  budget
- correct Qt microphone and playback ownership
- provider-neutral local and hosted operation
- typed-action isolation and reliable turn cancellation
- a concrete capability or maintenance benefit that Akiha's coordinator cannot
  reasonably provide
