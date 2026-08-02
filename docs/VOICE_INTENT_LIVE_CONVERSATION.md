# Voice Intent And Live Conversation Architecture

**Status:** Implementation in progress - V0 through V4 complete; V5 underway

**Planning date:** 2026-08-01

**First review incorporated:** 2026-08-01

**Architecture direction approved:** 2026-08-01

## Purpose

This document proposes the next voice architecture for Project Akiha. The work
is a post-Phase 8 architecture milestone, not part of the future Phase 9 Pet
Simulation Layer.

The architecture should make Akiha faster and more natural to talk with while
preserving the local-first voice path, provider choice, character identity,
and Phase 8 permission-gated assistant-action boundary.

The milestone must support two first-class provider choices behind the same
contracts, with three explicit processing modes:

- **Fully Local Modular:** local microphone processing, local STT, an Ollama or
  other configured local LLM, Akiha speech rendering, and local VOICEVOX
  playback.
- **Hybrid API Modular:** local microphone processing, local STT, an explicitly
  selected hosted text API, Akiha speech rendering, and local VOICEVOX
  playback.
- **Hosted Live:** an explicitly selected realtime provider such as Gemini
  Live, which may receive microphone audio and return native audio.

Installing a local LLM must not require a second chat, memory, action, or UI
architecture. Selecting a hosted API must not remove or weaken the local lane.
The Settings UI must disclose whether the selected mode sends text, audio, or
neither to a hosted provider.

It addresses four related but separate concerns:

1. Hearing speech quickly and reliably.
2. Understanding commands inside natural sentences.
3. Beginning spoken replies before a complete long response exists.
4. Supporting an optional low-latency live conversation provider.

This is an architecture and review document. Checked items record decisions
already agreed during planning. They do not claim that the implementation is
complete.

## Existing Baseline

Phase 7 already provides:

- user-started push-to-talk microphone capture
- local `faster-whisper` transcription
- adaptive endpoint detection tested with steady fan noise
- stabilized partial transcript previews
- confidence-aware final transcript handling
- automatic final transcript submission when confidence permits
- provider-neutral STT and TTS service boundaries
- local VOICEVOX synthesis and in-memory playback
- listening, thinking, speaking, muted, and error visual states
- Japanese canonical assistant responses with derived English subtitles
- speech-only identity styling with safe fallback

Phase 8 and the Spotify extension already provide:

- typed action contracts and validators
- capability- and target-scoped permissions
- deterministic local parsing for explicit commands
- bounded local target resolution
- ambiguity and confirmation handling
- audited execution with privacy-safe results
- an optional constrained LLM tool-proposal gateway
- ephemeral result and interaction context that does not become durable memory

The new system must extend these foundations rather than replace or bypass
them.

## Problems To Solve

### Hearing

The current partial-transcript path repeatedly asks `faster-whisper` to process
growing audio snapshots. It behaves like streaming in the UI but is not a true
incremental recognizer. Longer utterances can repeat work, delay revisions,
and produce unstable tails.

### Intent

Explicit commands work reliably, but many patterns still expect relatively
specific sentence shapes. Politeness, fillers, vocatives, corrections, and
extra conversational words can prevent an otherwise clear command from
matching.

### Speaking

The local path normally waits for the complete provider response before
synthesizing the full TTS result. This makes a correct answer feel slower than
necessary.

### Turn Taking

Listening, provider generation, synthesis, playback, and action execution have
separate cancellation behavior. Live conversation requires one coordinator to
own the turn and reject stale events after interruption.

## Goals

- [x] Keep push-to-talk as the default voice experience.
- [x] Add an optional user-started multi-turn Conversation Session.
- [x] Keep a complete local modular path using local STT and VOICEVOX.
- [x] Add Gemini Live only as an optional provider adapter.
- [x] Make provider-neutral contracts reusable by future realtime providers.
- [x] Show stable partial transcripts with lower repeated STT work.
- [x] Understand commands embedded in natural phrasing without substring-only
  execution.
- [x] Preserve deterministic parsing as the highest-priority offline fast path.
- [x] Let an LLM propose only typed, untrusted actions when local resolution is
  insufficient.
- [x] Start local speech from completed sentence or clause segments.
- [x] Support controlled interruption and end-to-end cancellation.
- [x] Keep final chat and memory content semantically consistent.
- [x] Keep microphone, transcript, provider, and action diagnostics
  privacy-safe.
- [x] Keep Spotify packaged verification independent from this architecture.
- [x] Close and package the modular voice track before beginning hosted live
  work.
- [x] Give the hosted live track its own later release gate.
- [x] Keep local LLM and hosted API support behind one provider-neutral
  conversation pipeline.
- [x] Pipeline recognition, intent preparation, generation, synthesis, and
  playback where their safety boundaries allow overlap.

## Non-Goals

- No always-on microphone at application startup.
- No wake word or continuous background listening.
- No replacement of local voice with a mandatory cloud service.
- No direct AI access to executors, files, applications, Spotify sessions, or
  permission repositories.
- No arbitrary shell, PowerShell, command-line, or administrator execution.
- No inference of companion, pet, or behavior state from dialogue keywords.
- No raw microphone-audio retention.
- No durable storage of partial transcripts or transient search results.
- No custom Akiha voice training in this milestone.
- No automatic provider fallback that silently changes where microphone audio
  is processed.
- No true local full-duplex mode until acoustic echo cancellation is proven.

## Fixed Design Rules

1. Voice transport does not own application permissions.
2. AI output is always untrusted input to the action system.
3. Only the existing typed action gateway can reach an executor.
4. Exact deterministic commands have priority over provider proposals.
5. One accepted action may execute at most once for a conversation turn.
6. Final transcripts are authoritative; partial transcripts are replaceable UI
   state.
7. An interrupted or incomplete assistant response is not eligible for memory
   extraction.
8. A spoken success message may only follow an actual successful action result.
9. Local paths, directory listings, Spotify library data, and device IDs are
   never automatically added to hosted-provider context.
10. Cloud microphone use is visible, explicit, and bounded to an active user-
    started session.
11. Partial transcripts may prepare intent candidates, but only an accepted
    final transcript may authorize routing, persistence, or action execution.
12. Exactly one explicitly selected processing lane owns a turn. A provider
    failure never silently reroutes microphone audio or text to another lane.
13. Hosted and local providers share canonical chat, memory, identity, action,
    interruption, and diagnostic contracts.

## User Experience Modes

### Push-To-Talk

Push-to-talk remains the default and lowest-surprise mode.

```text
user presses Talk
    -> capture begins
    -> partial recognition and safe intent preparation overlap with speech
    -> endpoint accepts one final transcript
    -> local action or provider response begins
    -> stable response segments synthesize and play while later text generates
    -> turn completes -> Idle
```

- Talk begins one recording.
- Local endpoint detection may finish the recording after silence.
- Manual Stop remains available.
- Low-confidence finals remain editable and are not sent automatically.
- The microphone closes after the turn.
- Partial transcript text remains visible while the user speaks, but it cannot
  execute an action or enter chat or memory before final acceptance.

### Local Conversation Session

The user explicitly starts a multi-turn session from Chat. Akiha alternates
between listening and speaking until the user ends the session.

Each turn uses the same pipelined processing model as push-to-talk. The session
reopens the microphone after completed local playback and repeats until the
user selects End conversation.

The first local implementation is coordinated half-duplex. Microphone capture
pauses during Akiha's playback to avoid transcribing VOICEVOX through speakers.
The user can click Talk while she is speaking to interrupt and begin a new
turn. Automatic speech-based interruption is deferred until echo cancellation
is reliable.

### Gemini Live Conversation Session

Gemini Live is an optional provider for a user-started conversation session.
It uses a persistent bidirectional connection for audio input, native audio
output, transcription, interruption, and constrained function proposals.

The adapter must follow the current official Gemini Live protocol rather than
leak protocol details into the coordinator:

- [Gemini Live capabilities](https://ai.google.dev/gemini-api/docs/live-api/capabilities)
- [Gemini Live best practices](https://ai.google.dev/gemini-api/docs/live-api/best-practices)
- [Gemini Live SDK guide](https://ai.google.dev/gemini-api/docs/live-api/get-started-sdk)
- [Gemini Live ephemeral tokens](https://ai.google.dev/gemini-api/docs/live-api/ephemeral-tokens)

The initial personal desktop implementation may use the user's existing Gemini
API key encrypted through the current Windows credential boundary. No Gemini
key is embedded in the application or repository. A future public distribution
must reassess direct client authentication and whether a token broker is
appropriate.

Gemini native audio will not sound identical to the selected VOICEVOX speaker.
Settings must label this tradeoff clearly. Users who prioritize the temporary
Akiha voice can remain on a Modular Voice path.

### Cost, Context, And Data-Use Boundary

Gemini Live does not have one dependable flat per-minute cost. Google currently
documents token billing against the active session context on every turn,
including accumulated prior audio tokens. Longer sessions can therefore cost
more per turn as their context grows. Enabling input or output transcription
also adds billed text output tokens. See the current
[Live API pricing and billing guidance](https://ai.google.dev/gemini-api/docs/live-api/best-practices#pricing-billing)
and [Gemini Developer API pricing](https://ai.google.dev/gemini-api/docs/pricing).

The first hosted implementation must therefore enforce all of these controls:

- a finite session-duration limit with no unlimited option
- a proposed default limit of 10 minutes and first-release maximum of 15
  minutes
- mandatory context-window compression with a conservative sliding window
- a visible remaining-time warning before the session ends
- bounded session resumption that cannot extend the logical duration limit
- privacy-safe turn and token-usage diagnostics when the provider supplies them
- no fixed currency estimate embedded in Akiha because model prices can change

The current Gemini Developer API pricing tables label free-tier content as
eligible to improve Google's products and paid-tier content as not used for
that purpose. Model availability and free quotas can change. Before every
release, the implementation must revalidate the current provider terms and
show a versioned notice that distinguishes the selected free or paid data-use
boundary. Akiha must not describe free-tier Live access as suitable for
unlimited daily use or promise that a particular Live model has a free quota.

## Top-Level Architecture

```text
Qt microphone -> Audio Capture Adapter -> bounded Audio Frame Bus
                                            |             |
                                            |             +-> Endpoint Detector
                                            |
                                            +-> selected lane
                                                |
              +---------------------------------+----------------------------+
              |                                                              |
        Modular Voice                                                    Hosted Live
        rolling local STT                                                 Gemini Live audio
        local intent preparation                                         hosted proposals
        Ollama/local LLM or                                               native/text response
        selected hosted text API
        streamed text response
              |                                                              |
              +----------------------+------------------+--------------------+
                                     |                  |
                              final transcript    untrusted intent/proposal
                                     |                  |
                                     |           Intent Arbiter
                                     |                  |
                                     |           Existing Typed Action Gateway
                                     |           validation -> permission
                                     |           -> confirmation -> execution
                                     |           -> sanitized audit
                                     |
                         canonical chat/memory accumulator
                                     |
                         stable response segmenter
                                     |
                  identity renderer and selected speech output
                         VOICEVOX or hosted native audio
                                     |
                             ordered playback
```

These stages are concurrent where possible; the diagram expresses ownership,
not a requirement that each box wait for the preceding turn to finish. The
coordinator owns voice-session lifecycle, turn IDs, lane selection, and
cancellation. It does not own filesystem, application, Spotify, or memory
repositories.

The local, hybrid, and hosted-live paths reconverge before persistence and
action execution. This keeps one authoritative chat and memory pipeline and
one permission boundary regardless of which provider is selected. In Hybrid
API Modular mode, microphone audio remains local but the accepted transcript
and bounded conversation context follow the selected hosted text provider's
existing privacy boundary.

## Provider-Neutral Contracts

The exact Python names may change during implementation, but the ownership
boundaries should remain stable.

### AudioFrame

Represents bounded, in-memory PCM captured from one microphone session.

Required metadata:

- session ID and turn ID
- monotonic sequence number
- monotonic capture timestamp
- sample rate, channel count, and sample format
- audio bytes

Audio bytes must never enter the general event logger. Provider adapters may
resample or reframe audio to their required format.

### TranscriptRevision

Represents replaceable recognition output.

Required metadata:

- session ID and turn ID
- revision number
- text
- partial or final status
- detected language when available
- coarse confidence (`unknown`, `low`, `medium`, or `high`)
- provider name
- endpoint reason for final revisions

Partial revisions may enter only the replaceable UI preview and speculative
intent-preparation path. Only an accepted final revision may commit intent,
enter chat, start translation or memory processing, or authorize an action.

### ConversationTurn

Tracks ownership across recognition, intent, generation, speech, and actions.

Required metadata:

- session ID and turn ID
- cancellation token
- user-input mode
- selected provider lane
- accepted final transcript
- action-decision state
- response-completion state
- interruption state

The turn object carries IDs and states, not service or executor references.

### LiveSessionAdapter

A provider-neutral live adapter should expose operations equivalent to:

- start with explicit configuration and cancellation ownership
- accept audio frames
- signal end of one user turn when required by the provider
- emit transcript revisions
- emit assistant text revisions when available
- emit audio frames
- emit constrained function proposals
- accept sanitized function results
- interrupt the active response
- stop and release the session

No UI or action executor may depend on Gemini-specific event classes.

### StreamingSpeechRecognizer

The local recognizer should expose operations equivalent to:

- start one recognition turn
- accept bounded audio frames
- emit partial transcript revisions
- finalize using the bounded utterance buffer
- cancel and discard late results

The existing batch `faster-whisper` provider remains available behind an
adapter as a fallback.

### ResponseSegment

Represents text that is stable enough to synthesize.

Required metadata:

- turn ID and ordered segment index
- canonical text span
- speech-rendered text
- final-segment flag

Segments cannot be reordered. Cancellation discards unsynthesized and queued
segments belonging to that turn.

### ActionProposal

All deterministic and provider-generated proposals converge on one structure:

- turn ID and unique proposal ID
- proposal source
- registered action name
- bounded arguments
- confidence or ambiguity state
- optional opaque local-result handles

Provider proposals never contain an executor, raw credential, permission
object, or unrestricted command line.

## V0 Pipeline Framework Evaluation

Before implementing the coordinator, run a bounded technical evaluation of
Pipecat against a small Akiha-owned orchestration layer. This is an adoption
checkpoint, not a commitment to replace existing services.

Pipecat is relevant because its frame pipelines, interruption handling,
provider adapters, and turn-management strategies match the proposed
concurrent architecture. Akiha must still retain ownership of Qt UI state,
canonical chat and memory, identity rendering, subtitles, permissions, typed
actions, audit history, and privacy policy.

The evaluation must prove or reject all of these points:

- Python 3.13 and Windows compatibility in the current environment.
- A Qt microphone input bridge without creating a competing audio owner.
- A Qt/audio-output bridge that preserves current device selection and stop.
- A custom VOICEVOX output adapter with ordered segments and cancellation.
- Ollama/local-LLM streaming through the provider-neutral response contract.
- Existing hosted text providers through the same modular response contract.
- Gemini Live adapter feasibility without Gemini event types entering UI or
  action code.
- Typed action proposals passing only through Akiha's existing gateway.
- Interruption, stale-turn rejection, and graceful shutdown behavior.
- Nuitka dependency size, startup time, hidden imports, and packaged audio
  behavior.

Pipecat's standard local Whisper integration is segment-oriented after VAD; it
does not by itself satisfy Akiha's requirement for useful transcript revisions
while the user is still speaking. The spike must therefore keep the planned
rolling recognizer or prove a better true-streaming local recognizer behind
`StreamingSpeechRecognizer`.

The outcome is one short decision record: adopt Pipecat, adopt selected
components only, or retain Akiha-owned orchestration. No production milestone
depends on Pipecat until this checkpoint is complete.

## Concurrent Session And Stage State

A single linear state machine would incorrectly imply that recognition,
generation, synthesis, and playback cannot overlap. State is therefore split
into one session lifecycle plus concurrent per-turn stage states.

### Session Lifecycle

```text
IDLE -> STARTING -> ACTIVE -> STOPPING -> IDLE
                         \-> ERROR -> STOPPING
```

- `IDLE -> STARTING` occurs only through an explicit user request.
- `STARTING -> ACTIVE` requires microphone or selected-provider readiness.
- `STOPPING` cancels every owned stage and performs bounded cleanup.
- `ERROR` records a sanitized failure and releases resources before recovery.

### Concurrent Turn Stages

```text
capture:      OFF | CAPTURING | ENDPOINTING | COMPLETE | CANCELLED | FAILED
recognition:  IDLE | PARTIAL | FINALIZING | FINAL | CANCELLED | FAILED
intent:       IDLE | SPECULATIVE | COMMITTED | CONFIRMING | COMPLETE | FAILED
generation:   IDLE | STREAMING | COMPLETE | CANCELLED | FAILED
synthesis:    IDLE | QUEUED | ACTIVE | COMPLETE | CANCELLED | FAILED
playback:     IDLE | BUFFERING | PLAYING | COMPLETE | CANCELLED | FAILED
```

Recognition may emit revisions while capture continues. Intent may build a
replaceable speculative candidate from stable partial text, but cannot commit
or execute it before final transcript acceptance. Generation may emit stable
segments while synthesis and playback process earlier segments.

The UI derives one dominant cue from these concurrent states instead of
owning the pipeline. A recommended priority is error, listening, confirming,
speaking, thinking, and idle. This preserves the existing mood indicator
without forcing the underlying workers into a false linear sequence.

Every callback includes its session ID and turn ID. Every ordered stream event
also includes a revision or segment index. A callback for a cancelled,
replaced, or completed turn is ignored. Cancellation fans out to every active
stage before a replacement turn may commit.

## Local Streaming Recognition

The first implementation should improve the existing `faster-whisper` path
without immediately adding another native dependency.

Proposed strategy:

1. Normalize microphone data into bounded mono PCM frames.
2. Keep a bounded in-memory rolling utterance buffer.
3. Transcribe overlapping recent windows on an adaptive cadence.
4. Compare consecutive hypotheses.
5. Commit only a stable shared prefix and keep a short replaceable tail.
6. Emit one authoritative final revision after endpoint detection.
7. Use the existing confidence policy before automatic submission.

This is still an emulated streaming recognizer, but it avoids repeatedly
processing the entire unbounded recording and gives the UI explicit revision
semantics.

Before adopting a different local engine, benchmark it against the rolling
adapter for:

- time to first useful partial
- finalization latency
- CPU and memory use
- English/Japanese command accuracy
- fan and room-noise behavior
- Python 3.13 and Nuitka packaging risk

A true streaming engine may be added later behind the same contract if it wins
the benchmark materially.

## Endpoint Detection

The current adaptive noise-floor and fan-resistant endpoint logic remains the
starting point.

Endpoint decisions should use audio evidence, not transcript punctuation.
Transcript stability may delay finalization briefly but cannot keep the
microphone open indefinitely.

Final endpoint reasons should be bounded values such as:

- sustained silence after speech
- manual stop
- recording timeout
- provider-reported end of turn
- cancellation
- device failure

The diagnostics layer may record the reason and coarse timing, never raw audio
or transcript content.

## Intent Router

The router uses three ordered stages.

### Stage 1: Deterministic Command Envelope

The parser should find one supported command inside a natural sentence while
accounting for:

- optional companion name or vocative
- politeness and modal verbs
- harmless fillers
- punctuation
- common STT aliases
- optional trailing purpose phrases

Examples that should resolve equivalently:

```text
Open Spotify.
Akiha, open Spotify.
Could you please open Spotify for me?
Akiha, would you mind opening the Spotify application?
```

This cannot be implemented as a simple substring check. The parser must reject
negation, hypothetical use, quoted commands, and informational or
metalinguistic questions.

Examples that must not execute:

```text
Do not open Spotify.
Tell me how to open Spotify.
Why did you open Spotify?
If I asked you to open Spotify, what would happen?
The phrase "open Spotify" is one of your commands.
```

### Stage 2: Ephemeral Context Resolver

The resolver handles references to recent, visible interaction state:

- `open the second one`
- `play that album`
- `pause it`
- `close the app`
- `open the folder inside it`

Context stores only bounded metadata and opaque identifiers. It expires after
a short duration, is cleared by New Chat or Clear Chat where appropriate, and
never becomes durable companion memory.

### Stage 3: Optional LLM Proposal

If deterministic and context resolution cannot produce one safe action, an
enabled provider may propose a registered action using a strict schema.

The proposal is not authorization. The local action gateway still performs:

```text
schema validation
    -> capability lookup
    -> local target resolution
    -> approved-root or allowlist check
    -> ambiguity handling
    -> confirmation when required
    -> execution
    -> audit result
```

If confidence is insufficient or multiple targets remain viable, Akiha asks a
concise question instead of guessing.

## Intent Arbitration And Duplicate Prevention

Local parsing and a live provider may both recognize the same turn. An
`IntentArbiter` must ensure at-most-once execution.

Priority order:

1. explicit confirmation response to an already pending action
2. exact deterministic local command
3. deterministic contextual follow-up
4. validated provider proposal

Once one proposal is accepted, the turn ledger records its action category and
proposal ID. Duplicate or conflicting proposals for that turn are rejected and
audited as non-executed decisions.

For Gemini Live, successful or failed action results are returned to the model
only as sanitized function results. The model must not claim completion before
the local executor reports success.

## Local Streaming Response And Speech

The Local Modular lane should not wait for the complete assistant response
before beginning TTS.

```text
streamed provider text
    -> canonical response accumulator
    -> sentence/clause stability detector
    -> speech-only identity renderer
    -> ordered VOICEVOX synthesis workers
    -> ordered playback queue
```

Rules:

- Only completed sentence or conservatively stable clause boundaries may be
  synthesized.
- The canonical provider response remains the chat and memory source.
- Speech styling may alter only the derived TTS text.
- A styling failure falls back to the canonical segment.
- A synthesis failure leaves the canonical text visible.
- A later segment may synthesize while an earlier segment plays, but playback
  order is fixed.
- Backpressure limits the number and duration of queued segments.
- Cancellation clears pending generation, synthesis, and playback for the
  interrupted turn.

English subtitle generation should occur from completed canonical Japanese
text. It must not delay the first spoken segment. Streaming subtitle
translation may be considered later if it can preserve stable ordering.

## Canonical Conversation And Memory Rules

### Local Modular Lane

- The accepted final STT result is the canonical user message.
- The completed provider response is the canonical assistant message.
- VOICEVOX text and audio are derived output.
- English subtitles are derived output.

### Gemini Live Lane

- The final input transcription is the canonical user message.
- The final output transcription is the canonical assistant message.
- Native audio is derived output and is not retained.
- If a valid output transcript is unavailable, the response is treated as
  audio-only and is excluded from memory extraction rather than replaced with
  invented text.

### Interrupted Turns

- Partial user transcripts are discarded when a turn is cancelled.
- An interrupted assistant partial may remain visible during the current UI
  session with an interrupted marker.
- Incomplete assistant output is not summarized or sent to memory extraction.
- Structured action results and audit records remain separate from durable
  personal memory.

## Interruption And Barge-In

### Controlled Local Interruption

When the user presses Talk while Akiha is speaking:

1. Stop the current audio sink.
2. Clear queued response segments and synthesized audio.
3. Cancel provider generation when supported.
4. Mark the assistant turn interrupted.
5. Start a new microphone turn.

An action that already completed is not reversed. An action that has not begun
execution should honor cancellation if its executor supports it.

### Gemini Live Interruption

The adapter may use provider-native interruption and VAD. It must still emit
the same coordinator events, clear client-side queued audio promptly, and mark
the interrupted response as incomplete.

Speech-based interruption should be enabled only after testing with speakers,
headphones, and realistic room noise. False interruption from Akiha's own audio
must fail safely.

## UI And Settings

Proposed Voice settings:

- Voice enabled.
- Input mode: Push-to-talk or optional Conversation Session.
- Session provider: Local Modular or Gemini Live.
- Microphone and output device.
- Local recognizer model and language.
- Local TTS endpoint, speaker, volume, and speaking rate.
- Automatic final transcript sending.
- Stable partial transcript preview.
- Silence endpoint duration and recording timeout.
- Controlled interruption enabled.
- Gemini Live model and native voice when that provider is selected.
- Hosted session duration limit: 5, 10, or 15 minutes; default 10.
- Hosted context compression enabled and not user-disableable.
- Remaining hosted-session time and provider-reported usage summary.
- Cloud audio privacy acknowledgement.

Chat should expose:

- Talk for a single turn.
- Start conversation for a multi-turn session.
- End conversation while a session is active.
- Stop voice or interrupt while Akiha is speaking.
- A stable listening/thinking/speaking status region.
- A visible cloud/local session label.
- An elapsed live-session indicator.

Controls should not shift the chat layout when their state changes.

## Privacy And Security

- Microphone capture starts only through an explicit user action.
- Conversation Session never starts automatically on application launch.
- The microphone is released when a session ends, fails, or the app exits.
- Raw audio remains in memory only for the active bounded operation.
- Partial transcripts are UI-only and are not persisted.
- Final transcript content follows the existing chat and local-data policy.
- Cloud audio is transmitted only while the selected hosted session is active.
- The hosted session has a finite duration and bounded context window.
- Switching from hosted to local processing requires visible user action or
  confirmation; it is never silent.
- User-supplied API keys use the existing Windows encryption boundary.
- No API key, OAuth token, audio content, transcript, local path, or Spotify
  library item is written to technical diagnostics.
- Hosted providers receive only user-supplied conversation content and the
  minimum tool schemas/results needed for the selected feature.
- Function results are sanitized before returning to a hosted live session.
- Existing permission grants remain capability- and target-scoped.

The first enablement of hosted live audio requires a versioned notice that
explains where audio is processed, when the microphone is active, what is
retained, how free- and paid-tier data use currently differs, how accumulated
session context affects billing, and how to end the session.

## Diagnostics

Privacy-safe metrics should include:

- selected local or hosted lane
- microphone/provider readiness
- coarse microphone state and level band
- endpoint reason
- time to first partial transcript
- number of transcript revisions
- finalization latency
- intent route (`deterministic`, `context`, `provider`, or `none`)
- ambiguity or confirmation state
- time to first provider text
- time to first synthesized or native audio
- queued speech-segment count
- interruption and cancellation outcome
- sanitized action outcome

Diagnostics must not include:

- raw or encoded microphone audio
- transcript or response text
- API keys or OAuth tokens
- local paths or directory listings
- Spotify library/search contents or device identifiers
- unrestricted provider exception bodies

## Failure And Fallback Behavior

| Failure | Required behavior |
| --- | --- |
| Microphone unavailable | Keep typed chat available and show a bounded error. |
| Local STT unavailable | Keep the final recording unsent; offer diagnostics. |
| Low-confidence final | Place editable text in Chat and require Send. |
| Provider generation fails | Preserve the user message and restore controls. |
| VOICEVOX fails | Keep the complete assistant text visible without speech. |
| Playback fails | Stop queued audio and leave Chat usable. |
| Gemini Live connection fails | End cloud capture visibly; do not silently switch providers. |
| Gemini session expires | Attempt bounded documented resumption or end cleanly. |
| Tool proposal is invalid | Reject locally and return a sanitized denial. |
| Action is ambiguous | Ask for one bounded clarification. |
| Action execution fails | Report the real failure; never claim success. |
| Shutdown during any state | Cancel workers, stop audio, release microphone, and close sessions. |

Typed chat, settings, tray controls, and the desktop pet must continue working
when every voice provider is unavailable.

## Concurrency And Resource Ownership

- Only one voice session may own the microphone at a time.
- Only one authoritative user turn may finalize at a time.
- A turn may own at most one accepted action execution.
- Audio capture, recognition, provider streaming, synthesis, and playback use
  separate bounded workers or asynchronous tasks.
- The coordinator owns cancellation tokens and session IDs.
- Provider adapters own their network/session resources.
- Playback owns only its current in-memory audio buffers.
- Executors remain owned by the existing assistant-action service.
- UI objects observe events and issue requests; they do not own worker logic.
- Shutdown waits for bounded cleanup and reports incomplete cleanup without
  exposing private content.

A future single-instance application guard may further protect microphone and
managed-provider ownership, but it is not introduced implicitly by this work.

## Automated Verification

### Session Foundation

- [x] Session-lifecycle and concurrent-stage transition tests.
- [x] Legal overlap tests for capture/recognition, generation/synthesis, and
  synthesis/playback.
- [ ] Tests proving speculative partial intent cannot persist or execute.
- [x] Turn-ID and stale-callback rejection tests.
- [ ] Cancellation during every active state.
- [ ] Shutdown and resource-ownership tests.
- [ ] Local/hosted adapter conformance tests using fakes.

### Hearing

- [ ] Stable-prefix commit and replaceable-tail tests.
- [ ] English and Japanese partial-growth tests.
- [ ] Corrections, false starts, short pauses, and long-pause tests.
- [ ] Fan noise, muted input, immediate speech, and noise-spike tests.
- [ ] Low-confidence review and final-transcript authority tests.
- [ ] Bounded buffer and repeated-work tests.

### Intent

- [x] Name, politeness, filler, punctuation, and suffix-envelope tests.
- [x] Negation, hypothetical, quoted-command, and metalinguistic rejection.
- [x] Context follow-up and context-expiry tests.
- [x] Ambiguity and confirmation tests.
- [x] Deterministic-versus-provider arbitration tests.
- [x] At-most-once action execution tests.
- [x] Hosted-provider local-data isolation tests.

### Speaking

- [x] Sentence and conservative clause segmentation tests.
- [x] Ordered synthesis and playback tests.
- [x] Backpressure and queue-bound tests.
- [x] Style-render fallback tests.
- [x] Interruption during generation, synthesis, and playback.
- [x] Canonical-text and derived-speech separation tests.

### Gemini Live

- [ ] Protocol adapter tests with a deterministic fake transport.
- [ ] Audio framing and resampling tests.
- [ ] Input/output transcript-finalization tests.
- [ ] Native audio queue and interruption tests.
- [ ] Function proposal and sanitized-result tests.
- [ ] Session timeout, resumption, disconnect, and quota-error tests.
- [ ] Explicit local/cloud switching and privacy-notice tests.

### Regression

- [ ] Existing Phase 7 voice tests remain green.
- [ ] Existing Phase 8 action tests remain green.
- [ ] Spotify deterministic command and selection tests remain green.
- [ ] Chat, memory, subtitles, mood states, and shutdown remain stable.

## Manual Verification

Source verification should cover:

- single-turn push-to-talk in English and Japanese
- natural commands with names, politeness, and extra words
- negated and informational command-like sentences
- fan-noise endpoint behavior
- local partial transcript speed and final correction
- low-confidence manual review
- local streamed VOICEVOX response ordering
- interruption while thinking and speaking
- local Conversation Session turn cycling
- Gemini Live start, conversation, interruption, and explicit end
- Gemini action proposal denial, confirmation, success, and failure
- microphone/provider failure recovery
- graceful quit during listening, generation, and speaking

Spotify receives its own standalone verification before implementation of this
architecture. After Milestone V5, build and smoke one Local Voice Intelligence
candidate. After Milestone V8, build and smoke a separate Hosted Live candidate.
Delete a previous confirmed package only after its intended replacement passes.

## Implementation Milestones

The milestones are split into two separately closeable tracks. V1 through V5
implement the Modular Voice pipeline for both Fully Local Modular and Hybrid
API Modular modes; they must not remain open while Gemini Live is added. The
modular track gets its own automated, manual, and packaged checkpoint before
V6 begins.

### Milestone V0: Pipeline Framework Spike

- [x] Build the smallest possible Pipecat spike using fake audio and provider
  adapters before integrating production UI.
- [x] Validate the Qt input/output bridge and single microphone/output
  ownership.
- [x] Validate rolling local transcript revisions rather than relying only on
  completed VAD segments.
- [x] Validate VOICEVOX segment synthesis, ordered playback, and cancellation.
- [x] Validate Ollama/local and hosted text providers through the same response
  event contract.
- [x] Validate typed action isolation with fake allow/deny results.
- [x] Measure Python 3.13, Windows, and Nuitka feasibility. The minimal Pipecat
  freeze exceeded 20 minutes and 2.7 GB of partial output without producing a
  runnable executable.
- [x] Retain Akiha-owned orchestration and do not add Pipecat as a dependency.
  See `docs/VOICE_PIPELINE_V0_DECISION.md`.

Progress and measured evidence: `docs/VOICE_PIPELINE_V0_EVALUATION.md`

**Checkpoint:** V1 does not begin until the orchestration ownership decision is
recorded. The spike may be discarded and must not mutate production data.

### Modular Voice Intelligence Track

### Milestone V1: Session Foundation

- [x] Add provider-neutral turn, transcript-revision, and live-session
  contracts.
- [x] Add `VoiceSessionCoordinator` with explicit state and cancellation.
- [x] Route current push-to-talk through the coordinator without changing
  behavior.
- [x] Route both Ollama/local LLM and existing hosted text APIs through the
  same modular response events.
- [x] Show the selected processing mode and its local-text/cloud-text/
  cloud-audio boundary in Settings.
- [x] Prove stale results cannot affect a replacement turn.

Replacement-turn proof includes active-worker cancellation, immutable turn
ownership for queued partial and final recognition audio, rejection of late
transcripts and failures, and acceptance of a valid result from the replacement
turn. Normal final-transcript delivery remains covered in production subscriber
order.

**Checkpoint:** Existing push-to-talk, STT, TTS, actions, and shutdown work
through the new coordinator before new behavior is enabled.

### Milestone V2: Local Hearing

- [x] Add bounded audio-frame and rolling-buffer ownership.
- [x] Implement the rolling `faster-whisper` recognizer adapter.
- [x] Emit explicit partial revisions and one authoritative final revision.
- [x] Preserve confidence gating and endpoint diagnostics.
- [x] Benchmark against the current cumulative-snapshot baseline.

Audio-frame ownership uses a production cumulative-snapshot bridge that emits
only appended PCM in bounded frames and retains only length plus a bounded
integrity digest between callbacks. `RollingAudioBuffer` then enforces one
session/turn owner, ordered frames, a fixed PCM format, monotonic timestamps,
and a strict in-memory duration limit before rolling recognition is enabled.
The production rolling adapter reuses `SpeechInputService`, requests bounded
overlapping recent windows for partial hypotheses, uses the retained bounded
utterance for final recognition, and releases PCM on finalization or
cancellation. It adds no microphone owner, model instance, or permanent worker.
The streaming recognizer applies the shared partial-stability policy, assigns
monotonic revision numbers, maps provider confidence into coarse privacy-safe
bands, and emits exactly one final revision with its endpoint reason. The
existing batch event bridge remains authoritative until the V2 switchover.
The production Qt controller now queues bounded frame batches through the
rolling recognizer and attaches each canonical revision to the existing voice
events. This preserves transcript-progress endpointing, low-confidence manual
review, privacy-safe microphone activity, auto-send behavior, and the batch
Settings microphone test without creating a second ledger authority.

V2 benchmark evidence: `docs/VOICE_RECOGNITION_V2_BENCHMARK.md`. The production
workload keeps the same 0.6-second first-partial cadence and final utterance,
while reducing repeated STT audio work by 52.1 percent at the 30-second limit.
The benchmark does not claim real-model accuracy or inference latency.

### Milestone V3: Natural Intent And Context

- [x] Add the tolerant deterministic command-envelope parser.
- [x] Add negative and metalinguistic guards.
- [x] Expand ephemeral reference context.
- [x] Add intent arbitration and at-most-once turn ledger.
- [x] Add optional typed provider proposal fallback.

The deterministic envelope parser is framework-free and runs before the
existing typed action parser. It removes only anchored companion-style modal,
politeness, filler, and courtesy wrappers, normalizes a narrow allowlist of
imperative gerunds, and rejects empty or oversized candidates. It does not use
substring execution, resolve targets, grant permission, or bypass the existing
action gateway. Its guard stage rejects anchored negated commands and bounded
metalinguistic, informational, hypothetical, and quoted-command forms before
wrapper removal. Rejection reasons are privacy-safe categories; command target
text is not included.

The local ephemeral resolver now gives exactly one latest validated result set
ownership of numbered or ordinal references, preventing stale result stores
from competing for phrases such as `open the second one`. It also supports a
recent validated album or playlist, Spotify playback pronouns, the last
successfully launched allowlisted application, and named child-directory
navigation beneath the recent approved directory. Entries expire after five
minutes and are cleared on New Chat, Clear Chat, or settings reconfiguration.
Only bounded metadata, local paths, and opaque service identifiers are held in
memory; this context is never persisted or sent to companion memory. An
unnamed child folder remains ambiguous and produces a clarification instead of
guessing.

Each submitted message now receives an opaque intent-turn ID. Exact and
contextual local routing closes before a hosted proposal becomes eligible, and
the bounded `IntentTurnLedger` accepts at most one action category for that
turn. Later duplicate or conflicting callbacks are recorded as non-executed
privacy-safe decisions. Ledger records contain only turn ID, proposal ID,
action category, source, and decision reason; they never contain user text,
paths, action parameters, or provider output. File-opening confirmation resumes
the already accepted action rather than creating a second proposal.

The optional JSON provider fallback now runs only after local parsing and
context resolution fail. It is disabled by default, rejects negated,
metalinguistic, quoted, oversized, or non-action input before contacting the
selected provider, and accepts only exact path-free schemas for allowlisted
applications, named directory lookup, passive media lookup, `none`, or a typed
clarification topic. Clarification text is rendered locally. Approved roots,
search results, paths, action parameters, and durable memory are never added to
provider proposal messages. Returned proposals still pass through local target
resolution, permissions, confirmation, execution, audit, and intent
arbitration. Provider-native function calling remains deferred to V7.

### Milestone V4: Streaming Local Speech

- [x] Stream canonical provider text into a stable response segmenter.
- [x] Render speech identity per stable segment with fallback.
- [x] Add bounded concurrent synthesis and ordered playback.
- [x] Preserve final canonical response and derived subtitle behavior.
- [x] Add controlled Talk-to-interrupt behavior.

Talk remains available while provider generation, local synthesis, or playback
is active. A valid Talk request synchronously stops derived speech, clears the
bounded segment/audio queue, cancels only unfinished chat, action, or proposal
workers, marks an interrupted partial assistant response in the current UI,
and then assigns the microphone to a new push-to-talk turn. Completed desktop
and Spotify actions are not reversed. If microphone input is unavailable, the
current output is preserved and the existing input diagnostic is shown; the
button remains a bounded Stop voice control instead.

### Milestone V5: Local Conversation Session

- [x] Add explicit Start conversation and End conversation controls.
- [x] Reopen the microphone after completed local playback.
- [x] Keep local turn taking half-duplex.
- [x] Add idle/session timeout and visible elapsed state.
- [x] Verify that the session never starts on application launch.

The Chat composer now exposes a fixed-width Start conversation / End
conversation control. Start is available only when configured microphone input
is idle and always requires a user click; constructing or launching the
application does not publish a session-start or microphone event. An explicit
start reserves one persistent coordinator session and opens its first turn as
`local_conversation`. Accepting or cancelling that microphone turn releases
turn ownership without discarding the session. End remains available while
the chat is busy and cancels unfinished input, output, generation, or action
work before closing the coordinator. A voice-session failure also clears the
visible active state.

Natural completion of the final assistant-response audio now emits one
privacy-safe playback-complete event from either the streaming segment queue
or the completed-response fallback path. While an explicit local conversation
session remains active and owns no current turn, that event reopens the
microphone as a new `local_conversation` turn. Replay, proactive speech,
cancelled output, late callbacks, duplicate completion events, and playback
outside an active session cannot trigger reopening. The event contains only a
bounded source and delivery category; it carries no response text or audio.

Voice operation ownership now enforces local half-duplex independently of UI
timing. An input-owned listening or transcript-finalization operation rejects
TTS acquisition, and an output-owned synthesis or playback operation rejects
direct microphone acquisition. These bounded rejections do not terminate a
valid microphone session. Automatic session reopen also requires that no chat,
action, or tool-proposal worker remains unfinished. Controlled Talk remains
the explicit exception: it stops output, cancels unfinished work, and only then
requests microphone ownership.

Local sessions now use monotonic elapsed and user-idle clocks. The default
idle limit is 120 seconds and the default total limit is 30 minutes; both are
bounded and configurable under Voice > Local conversation. Only a non-empty
final user transcript resets idle time, so timer ticks and automatic
microphone reopening cannot keep an abandoned session alive. Reaching either
limit cancels active voice or generation work, closes the coordinator, and
shows a bounded reason in Chat. A fixed-width `Local MM:SS` indicator exposes
elapsed time without shifting the composer controls. Session-state events
contain timing and lifecycle metadata only, never transcript or audio content.

V5 lifecycle regression coverage now exercises the complete local sequence:
explicit start, accepted final transcript, assistant output, natural completion,
microphone reopen under the same session with a fresh turn ID, and explicit
end. It also covers input and output timeout cleanup, coordinator-error cleanup,
busy-start rejection without interruption, duplicate and late playback events,
idempotent shutdown, and privacy-safe state payloads. A coordinator failure now
uses the same bounded cleanup path as End, preventing microphone ownership from
surviving after the visible session has closed.

### Modular Track Release Gate

- [x] Run the full automated suite and local voice regression checks.
- [ ] Complete local push-to-talk, natural intent, streaming speech,
  interruption, and Conversation Session manual checks.
- [ ] Build and validate a Local Voice Intelligence standalone candidate.
- [ ] Complete packaged microphone, faster-whisper, Ollama, one configured
  hosted text provider when available, VOICEVOX, actions, and graceful-
  shutdown smoke tests.
- [ ] Record measured latency baselines and remaining local limitations.

**Checkpoint:** The modular track is closed before hosted live implementation
begins. A failure or delay in Gemini Live must not keep local or hybrid API
improvements in an unfinished state.

### Hosted Live And Provider Tools Track

### Milestone V6: Gemini Live Conversation

- [ ] Add the Gemini Live adapter behind `LiveSessionAdapter`.
- [ ] Add native audio, input transcription, and output transcription paths.
- [ ] Add provider-native interruption with coordinator reconciliation.
- [ ] Add bounded session timeout/resumption behavior.
- [ ] Require context-window compression and the finite session-duration cap.
- [ ] Add explicit cloud-audio notice, settings, and diagnostics.
- [ ] Revalidate and disclose current free- versus paid-tier data use.
- [ ] Preserve Local Modular as an independent fallback choice.

### Milestone V7: Provider-Neutral Typed Tool Proposals

- [ ] Expose only allowlisted action schemas.
- [ ] Treat function calls as untrusted `ActionProposal` values.
- [ ] Reuse validation, permission, confirmation, execution, and audit.
- [ ] Return only sanitized function results.
- [ ] Add Gemini Live function proposals behind the provider-neutral adapter.
- [ ] Add Ollama tool proposals when the selected local model reports tool-call
  support.
- [ ] Fall back to deterministic and JSON proposal paths when a provider model
  does not support native tools.
- [ ] Prevent duplicate deterministic and provider execution for one turn.

Ollama officially supports tool calling for compatible models. Its tool calls
remain proposals and receive no additional authority. See
[Ollama tool calling](https://docs.ollama.com/capabilities/tool-calling).

### Milestone V8: Hosted Live Release Gate

- [ ] Run the full automated suite and quality checks.
- [ ] Complete the manual Gemini Live and provider-tool roundup.
- [ ] Reconcile privacy, security, architecture, and release documentation.
- [ ] Build and validate one standalone candidate.
- [ ] Complete packaged microphone, Gemini, provider tools, local fallback,
  actions, and shutdown smoke tests.
- [ ] Retain only the confirmed replacement package.

## Approved Architecture Decisions

1. Push-to-talk remains the default; Conversation Session is optional and
   user-started.
2. Local Modular remains the primary identity-preserving lane.
3. Gemini Live is an optional low-latency lane with its own native voice.
4. Local Conversation Session starts half-duplex.
5. Rolling `faster-whisper` is implemented and measured before adding another
   local STT dependency.
6. Exact deterministic intent has priority over LLM proposals.
7. Hosted and local-model tool proposals use the existing typed action gateway
   without direct executor access.
8. Final transcripts are canonical; partial and interrupted content do not
   enter memory extraction.
9. Cloud failure never causes a silent processing-location switch.
10. Spotify, the local voice track, and the hosted live track each receive an
    independent packaged release gate.
11. Gemini Live uses mandatory context compression and a finite 10-minute
    default, 15-minute maximum session in its first release.
12. Provider data-use terms and pricing are revalidated before release instead
    of hardcoding a per-minute cost promise.
13. The implementation remains a Post-Phase 8 architecture milestone rather
    than being renumbered as the Pet Simulation phase.
14. Fully Local Modular, Hybrid API Modular, and Hosted Live modes share one
    coordinator, canonical conversation pipeline, and typed action gateway.
15. Transcription remains present and becomes progressive; an accepted final
    transcript is still required for persistence and action commitment.
16. V0 rejected Pipecat as a production dependency. Akiha retains ownership of
    orchestration and carries the validated concurrency, bridge, and
    cancellation patterns into V1.

## Remaining Open Questions For Reviewers

1. Are the session lifecycle, concurrent stage states, and derived UI priority
   sufficient without provider-specific branches leaking into UI code?
2. Should local rolling Whisper be the first incremental recognizer, or is a
   different Windows/Nuitka-compatible streaming engine compelling enough to
   benchmark before implementation?
3. Is controlled half-duplex the correct first local Conversation Session, or
   should acoustic echo cancellation be pulled into the initial scope?
4. Is the deterministic/context/provider arbitration order correct?
5. Does the at-most-once turn ledger adequately prevent duplicate local and
   provider function execution?
6. Should provider-native tool calling land only after conversation-only
   Gemini Live sessions pass a separate internal checkpoint inside V6?
7. Are final input/output transcriptions sufficient canonical records for the
   Gemini Live lane?
8. Should an interrupted assistant partial remain session-visible, or be
   removed immediately?
9. Are any diagnostics listed above capable of revealing private content
   indirectly?
10. Which latency budgets should become formal exit criteria after measuring
    the current machine?
11. Does the architecture remain sufficiently provider-neutral for a future
    OpenAI Realtime, local speech-to-speech, or custom voice adapter?

## Exit Criteria

This architecture milestone is complete only when:

- the decisions above are reviewed and explicitly accepted or revised
- the provider-neutral contracts and state ownership are unambiguous
- local and hosted privacy boundaries are documented
- intent execution remains mechanically confined to the typed action gateway
- each implementation milestone has objective automated and manual checks
- unresolved questions are either answered or placed in a named backlog
- Spotify's independent replacement package passes its release verification
- the Modular Voice Intelligence package passes before hosted live work begins
- the Hosted Live package passes its separate final smoke verification
