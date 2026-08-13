# Voice Intent And Live Conversation Architecture

**Status:** V0 through V8 complete - Voice Intelligence roadmap closed

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
  See [Consolidated V0 Decision And Evidence](#consolidated-v0-decision-and-evidence).

Measured evidence is retained in the consolidated V0 appendix in this document.

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

V2 benchmark evidence is retained in the consolidated V2 appendix below. The production
workload keeps the same 0.6-second first-partial cadence and final utterance,
while reducing repeated STT audio work by 52.1 percent at the 30-second limit.
Endpointed workers now buffer any frames queued behind the last live partial
without running more partial inference, then perform exactly one authoritative
final transcription. This removes redundant post-silence Whisper passes while
preserving progressive preview behavior during active listening.
Queued live-preview batches are also coalesced: every PCM frame is retained,
but only the newest cumulative state triggers inference. Local interactive
recognition uses greedy decoding (`beam_size=1`) to bound CPU latency; the
canonical final transcript, confidence review gate, and provider boundary are
unchanged.
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

Natural command envelopes now apply consistently across allowlisted application
launch/close actions and every Spotify action family. Bounded leading requests,
polite suffixes, and trailing Akiha vocatives are removed before strict typed
parsing, so forms such as `Can you open VLC for me, Akiha?` retain the same
action contract as `Open VLC`. Spotify volume also accepts explicit absolute
forms such as `increase music volume to 50%`. This remains anchored envelope
normalization, not arbitrary substring execution; negative and metalinguistic
guards continue to run before any typed action can be created.

Spotify volume requests now preserve an explicit typed distinction between an
absolute `volume_percent` and a relative `volume_delta_percent`. A relative
request resolves the current active-device volume locally, applies one bounded
non-zero delta, clamps the result to `0..100`, and issues the existing Spotify
volume action. Both modes share the same playback permission and audit path;
the validator rejects requests containing both modes, neither mode, zero, or
an out-of-range value. Hosted providers never receive device volume state.

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

Post-V5 contextual correction now records only successful, sanitized action
identifiers plus coarse Spotify playback state. While that context is fresh,
the local resolver can conservatively recover pronunciation and
language-detection variants such as `Paue MIZIK` after playback or
`Continua la música` after a successful pause. Resolution requires one strong
context-compatible candidate; competing pause/resume-style candidates produce
a fixed local clarification, and unrelated music conversation falls through
without execution. Context expiry, chat reset, settings changes, or closing
Spotify remove the correction state.

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
applications, named directory lookup, passive media lookup, bounded Spotify
playback, `none`, or a typed clarification topic. Clarification text is
rendered locally. The model receives the current action sentence and only
coarse expiring labels for recent action, allowlisted application,
directory-context presence, and Spotify `playing` / `paused` state. Approved
roots, conversation history, search results, paths, action parameters, Spotify
library data, device IDs, and durable memory are never added to provider
proposal messages. Returned proposals still pass through local target
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

Assistant actions complete without producing assistant-reply playback. Their
worker cleanup therefore emits a separate privacy-safe turn-complete event
after the action is no longer active. An explicit local Conversation Session
uses that event to reopen the microphone through the same guarded resume path;
the event contains only the bounded `assistant_action` source category and
cannot bypass session, voice-ownership, or unfinished-work checks.

While local conversation mode is explicitly active, each accepted final
transcript is submitted to the canonical chat pipeline automatically even when
single-turn Talk is configured to leave transcripts editable. This temporary
session behavior ends with the conversation and does not change the saved
single-turn setting. Low-confidence finals still require manual review and can
never be auto-submitted merely because conversation mode is active.

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
microphone events cannot keep an abandoned session alive. Idle expiry is
deferred while final recognition, provider generation, synthesis, or playback
owns legitimate work. Natural assistant playback completion starts one fresh
user-response window when it reopens the microphone; duplicate completion
events cannot extend it. Reaching either limit cancels active voice or
generation work, closes the coordinator, and shows a bounded reason in Chat. A
fixed-width `Local MM:SS` indicator exposes
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

Manual V5 latency investigation found that queued 0.6-second preview frames
could each trigger obsolete Whisper work when inference fell behind capture.
The production worker now retains that backlog without replaying every partial
pass and recognizes only its latest cumulative state before finalization. Real
latency remains a release-gate measurement rather than a documentation claim.

### Modular Track Release Gate

- [x] Run the full automated suite and local voice regression checks.
- [x] Complete local push-to-talk, natural intent, streaming speech,
  interruption, and Conversation Session manual checks.
- [x] Build and validate a Local Voice Intelligence standalone candidate.
- [x] Complete packaged microphone, faster-whisper, Ollama, one configured
  hosted text provider when available, VOICEVOX, actions, and graceful-
  shutdown smoke tests.
- [x] Record measured latency baselines and remaining local limitations.

#### Source Verification And Latency Record

The 2026-08-08 source-application roundup confirmed push-to-talk, local
Conversation Session turn cycling, automatic action-turn resume, contextual
Spotify controls, natural command phrasing, streamed VOICEVOX output,
interruption, and fan-noise endpoint behavior. Contextual correction also
resolved bounded pronunciation and transcription errors without bypassing the
typed action gateway, while ambiguous requests remained clarification-first.

User-observed finalization latency for short English turns after the stale
preview-work fix was approximately two to three seconds from the end of speech
to the submitted final transcript. Earlier affected turns took roughly seven
to twenty-five seconds when obsolete partial-recognition work accumulated.
These are practical observations on the development machine, not a controlled
cross-hardware benchmark, and they exclude provider response generation and
speech synthesis time.

Remaining local limitations are explicit:

- local Conversation Session remains half-duplex rather than simultaneous
  full-duplex audio;
- final intent still depends on faster-whisper text, so unclear pronunciation
  can require contextual correction or user clarification;
- uncommon free-form paraphrases outside deterministic coverage need the
  optional bounded provider-proposal path;
- response time still varies with Whisper model size, CPU load, provider
  latency, response length, VOICEVOX synthesis, and audio-device conditions;
- the configured idle and total session limits remain intentional resource and
  privacy bounds rather than an always-open microphone mode.

#### Packaged V5 Closure Record

The final modular candidate was built on 2026-08-08 at:

```text
dist/nuitka-v5-local-voice-final/main.dist/Akiha.exe
```

The clean Python 3.13/Nuitka build completed with 1,199 automated tests passing
and three optional tests skipped. Ruff, Black, compilation, Windows GUI
subsystem validation, packaged dependency validation, and fresh-data plus
existing-data automated smoke checks passed.

The user then confirmed the complete manual packaged checklist: startup, local
voice, configured provider behavior, multi-turn Conversation Session,
contextual intent correction, permission-gated actions, and graceful Quit all
passed. This closes the V5 Modular Track release gate. V6 may begin without
changing or reopening the complete local modular lane.

**Checkpoint:** The modular track is closed before hosted live implementation
begins. A failure or delay in Gemini Live must not keep local or hybrid API
improvements in an unfinished state.

### Hosted Live And Provider Tools Track

### Milestone V6: Gemini Live Conversation

- [x] Add the SDK-neutral Gemini Live adapter behind `LiveSessionAdapter`.
- [x] Add native audio, input transcription, and output transcription paths.
- [x] Add provider-native interruption with coordinator reconciliation.
- [x] Add bounded session timeout/resumption behavior.
- [x] Require context-window compression and the finite session-duration cap.
- [x] Add explicit cloud-audio notice, settings, and diagnostics.
- [x] Revalidate and disclose current free- versus paid-tier data use.
- [x] Preserve Local Modular as an independent fallback choice.

#### V6A: Live Foundation - Complete

- [x] Add explicit hosted-live response modality and capability contracts.
- [x] Require hosted-live processing mode and a finite 15-minute maximum in
  `LiveSessionConfig`.
- [x] Add privacy-safe lifecycle events and bounded error codes.
- [x] Add a Gemini-specific transport protocol that cannot leak SDK classes
  into application controllers, UI, actions, chat, or memory.
- [x] Add `GeminiLiveSessionAdapter` with one-session and one-turn ownership.
- [x] Translate provider input transcripts, output transcripts, and native PCM
  frames into canonical Akiha contracts.
- [x] Reject wrong-session, wrong-turn, stale, cancelled, and unsupported audio
  input before transport dispatch.
- [x] Keep provider-native tool results disabled until V7.
- [x] Add an in-memory fake Gemini transport for deterministic lifecycle,
  cancellation, failure, and stale-event tests.
- [x] Keep V5 startup and the Local Modular lane unchanged.

The V6A adapter is deliberately SDK-neutral and performs no network access.
The current Google reference model name is represented by the configurable
default `gemini-3.1-flash-live-preview`; no preview model name is part of the
provider-neutral core contract. The concrete Google Gen AI SDK transport and
credential wiring belong to V6B, after its dependency and packaging impact are
measured.

V6A follows the current official protocol boundary: realtime audio is sent as
raw PCM through a persistent session, input and output transcriptions are
optional setup features, and audio output is 24 kHz PCM. Akiha requires input
to be prepared as mono 16-bit 16 kHz PCM before it enters the adapter. Because
the existing Qt microphone owner already captures that exact format, V6B uses a
bounded chunker and rejects nonconforming input instead of adding a CPU-heavy
resampler.

#### V6B: Native Audio Transport - Complete

- [x] Add the optional Google Gen AI SDK dependency behind the live extra.
- [x] Implement the concrete async Gemini transport.
- [x] Convert bounded Qt microphone frames to mono 16-bit 16 kHz PCM.
- [x] Send 20-100 ms realtime chunks through one bounded queue.
- [x] Receive 24 kHz native PCM into the existing single Qt playback owner.
- [x] Prove queue backpressure, cancellation, and shutdown without microphone
  or playback resource duplication.

V6B uses the optional `google-genai>=2.17,<3` extra. The dependency is imported
lazily, and Google SDK objects remain inside `GoogleGenAILiveTransport`. Akiha's
existing Qt microphone emits direct 20 ms mono PCM16 frames; the canonical
realtime bridge adds session, turn, time, and sequence ownership without
retaining cumulative audio. `GeminiPcmInputChunker` combines those frames into
40 ms provider chunks and sends them through a bounded asynchronous queue.

Native 24 kHz PCM responses are converted into short 200 ms in-memory WAV
segments and passed to the existing `VoicePlaybackController` and Qt audio
owner. V6B does not create a second microphone or playback device. Queue
overflow fails visibly, cancellation drops pending audio, stale playback
callbacks are ignored, and shutdown closes worker tasks and releases queued
buffers. Raw audio and credentials are never written to diagnostics or local
persistence.

This checkpoint verifies the concrete SDK boundary with deterministic SDK-shaped
fakes. It does not perform a real Gemini network call, expose Gemini Live in
Settings, or rebuild the packaged application. Transcript integration begins in
V6C; interruption, session controls, privacy UI, and release verification remain
in their later V6 checkpoints.

#### V6C: Live Transcripts - Complete

- [x] Map interim and final input transcription revisions.
- [x] Map output transcription revisions for canonical chat persistence.
- [x] Persist only accepted finals; never persist raw audio or partial text.

The Google transport now normalizes incremental input and output transcription
fragments into cumulative provider-neutral revisions, including detected input
language when available. `LiveTranscriptController` rejects wrong-session,
wrong-turn, stale, duplicate, and post-final revisions. Input revisions must
also pass the existing `VoiceSessionCoordinator` and `VoiceTurnLedger`
authority before they can become canonical.

Partial input and assistant revisions are exposed only through replaceable
preview callbacks. Provider turn completion does not immediately persist text,
because Gemini transcription events are independently ordered and a valid final
may arrive after `turn_complete`. The explicit commit gate waits for the
accepted final user transcript and final assistant transcript, then calls the
existing `ChatController` persistence and memory boundary exactly once.
An unknown persistence failure is terminal for that live turn and is not
silently retried, preventing a partially written message from being duplicated.

An audio-only response requires an explicit fallback decision. In that case,
the accepted final user transcript may be persisted, but no assistant text is
invented and the incomplete exchange is excluded from memory extraction.
Cancelled turns discard their transcript state. Raw audio and partial text are
never passed to repositories, summaries, exports, or memory processing.

V6C verifies this boundary with deterministic provider and repository tests. At
that checkpoint it did not expose Gemini Live in Settings, create the full
application event sink, or rebuild the packaged app. Provider-native
interruption followed in V6D, while application lifecycle composition and
user-facing Settings remain divided between V6E and V6F.

#### V6D: Live Interruption - Complete

- [x] Reconcile provider-native interruption with the turn ledger.
- [x] Cancel/truncate stale output and reject late audio or text.

Gemini Live now runs with automatic activity detection disabled so Akiha's
existing endpoint owner remains authoritative. The concrete transport sends
explicit `activity_start` and `activity_end` signals around local microphone
turns. Starting replacement user activity uses Gemini's
`START_OF_ACTIVITY_INTERRUPTS` behavior instead of inventing an unsupported
stop-generation request.

`HostedLiveInterruptionController` performs local cancellation before waiting
for the provider: it stops native playback, discards the interrupted
transcript state, marks the old ledger turn interrupted, and transfers
transcript ownership to a new turn. The Gemini adapter then quarantines old
assistant text, audio, and completion events until one matching provider
interruption confirmation arrives. Duplicate, mismatched, and late callbacks
cannot regain ownership. Provider connection failures still terminate the
session visibly rather than being hidden by a pending interruption.

Interrupted partial transcripts and audio are never persisted, exported, or
sent to memory extraction. This checkpoint is covered with deterministic
transport, adapter, ledger, transcript, playback, failure, and late-event
tests. It does not yet expose hosted live mode in Settings or compose the full
application event sink; those user-facing session controls begin in V6E. No
real Gemini network call or packaged rebuild is part of this checkpoint.

#### V6E: Session Management - Complete

- [x] Add explicit Start/End hosted conversation controls.
- [x] Add finite duration, context compression, resumption, `GoAway`, and
  reconnect behavior without extending the logical session limit.

`HostedLiveSessionController` now provides the application-level Start and End
ownership boundary for one hosted conversation. It reserves the canonical
coordinator session before connecting, requires the provider config to use that
same session identity, forwards only provider-neutral events, and synchronizes
explicit stop, timeout, provider failure, and shutdown with the existing
coordinator. The current chat UI remains on the Local Modular lane until V6F
can present hosted mode together with its required cloud-audio notice and
processing-location controls.

The Gemini adapter starts one monotonic logical deadline before the initial
connection attempt. Its provider configuration requires context-window
compression and session resumption, while `LiveSessionConfig` retains the hard
15-minute maximum. A connection rotation never creates a second deadline or
extends the first one. The planned V6F Settings values remain 5, 10, or 15
minutes with a 10-minute default.

Gemini session-resumption updates are translated into bounded events. Only the
latest resumable handle is retained, it remains memory-only and excluded from
dataclass representations, and a non-resumable update revokes the previous
handle. `GoAway` and an unexpected retryable connection close can reconnect
only when a current handle exists and the logical deadline has not passed.
Reconnect is capped at two attempts with a short bounded delay. Microphone
frames are rejected while reconnecting, raw audio is not replayed, and terminal
failure closes provider resources immediately while preserving a sanitized
error state for the application.

The transport recognizes the official `session_resumption_update` and
`go_away.time_left` messages and supplies the current handle only in the next
SDK connection setup. This checkpoint is covered by deterministic Start/End,
deadline, reconnect, retry exhaustion, handle revocation, input rejection,
cleanup, and coordinator tests. It performs no real Gemini call and does not
rebuild the standalone package.

References:

- [Gemini Live session management](https://ai.google.dev/gemini-api/docs/live-api/session-management)
- [Google Gen AI Python SDK](https://googleapis.github.io/python-genai/genai.html)

#### V6F: Privacy, Settings, And Diagnostics

- [x] Add the versioned cloud-audio notice and processing-location labels.
- [x] Add model, voice, session duration, and diagnostic settings.
- [x] Revalidate current Gemini availability, quota, pricing, and data-use
  language before release.

V6F added a second acknowledgement version dedicated to microphone audio sent
to Gemini Live. It is independent from the general first-run privacy notice,
is stored as non-sensitive configuration, and is required before Settings can
save Gemini Live as the conversation-session provider. The notice states when
streaming begins and ends, which transcript forms may be persisted, and that a
5, 10, or 15 minute application limit is not a fixed-price guarantee.

Voice Settings now persist the selected Local Modular or Gemini Live lane, the
Gemini Live model, native voice, and finite session duration. They visibly
label hosted audio as off-device processing and show context compression and
bounded session resumption as mandatory safeguards rather than disableable
options. The hosted readiness check inspects only local SDK, encrypted-key,
consent, model, voice, and duration state. It never connects to Google, opens
the microphone, logs a credential, or exposes transcript content.

As revalidated on 2026-08-10, Google's official pricing page lists
`gemini-3.1-flash-live-preview` as a low-latency audio-to-audio model. Its free
tier is labeled free of charge with content used to improve Google products;
the paid tier is token-metered and labeled as not used to improve Google
products. Availability, quotas, pricing, and terms remain provider-controlled
and must be checked again before a release.

V6F exposes and persists hosted setup but does not silently replace the current
Local Modular conversation runtime. Runtime lane selection and explicit local
fallback behavior remain the V6G checkpoint.

References:

- [Gemini Developer API pricing](https://ai.google.dev/gemini-api/docs/pricing)
- [Gemini Live capabilities](https://ai.google.dev/gemini-api/docs/live-api/capabilities)
- [Gemini API terms](https://ai.google.dev/gemini-api/terms)

#### V6G: Local Fallback

- [x] Preserve push-to-talk, Local Conversation, Ollama, hosted text, and
  VOICEVOX as explicit independent choices.
- [x] Never silently send local audio or text to Gemini after a failure.

V6G added an explicit `ConversationRuntimeRouter` that starts exactly the lane
selected in Voice Settings. The existing Talk path remains Local Modular:
microphone frames go to faster-whisper, accepted text goes to the separately
selected local or hosted text provider, and optional speech goes to VOICEVOX.
The Start conversation control now selects either that existing Local Modular
session or Gemini Live. The chat surface visibly labels the active lane as
`Local` or `Cloud` and shows its elapsed time.

Gemini Live owns a persistent asyncio session on a dedicated Qt worker. Direct
20 ms PCM microphone frames enter only that worker and never enter local STT.
Provider interim transcripts remain ephemeral; accepted final input/output
transcripts use the V6C canonical chat persistence path. Native response audio
reuses Akiha's existing Qt playback owner. The selected Gemini voice and Akiha
identity system instruction are passed in the live connection setup. Cloud
barge-in transfers turn ownership locally before requesting provider-native
interruption, so stale transcript and audio callbacks cannot regain authority.

The router contains no automatic cross-lane start operation. A Gemini startup,
stream, endpoint, playback, or shutdown failure ends the Cloud session visibly
and clears its resources without starting Local Modular or sending transcript
text through a different provider. Changing the selected lane in Settings ends
an active conversation first; starting the newly selected lane remains a
separate visible user action. Typed chat, Settings, tray/pet controls, local
push-to-talk, Ollama, hosted text APIs, and VOICEVOX remain independent.

This checkpoint added deterministic lane-selection, failed-start, direct-audio,
Qt worker lifecycle, shutdown, voice/system-config, visible-label, and barge-in
coverage. No standalone rebuild or real Gemini network call belongs to V6G;
those checks remain V6H and the final release gate remains V8.

#### V6H: Verification

- [x] Complete fake-protocol, native audio, transcript, interruption,
  resumption, privacy, fallback, and real-provider manual checks.
- [x] Keep final hosted-live packaging deferred to the V8 release gate.

V6H closed on 2026-08-10 after the complete automated suite passed with
1,284 tests and 3 optional-environment skips. The final corrective pass fixed
bursted native-audio queue capacity, promoted provider transcript fragments at
the Gemini turn boundary when the optional `finished` marker was absent,
prevented missing provider transcripts from stranding the next turn, preserved
privacy-safe provider operation errors, and isolated Hosted Live session
ownership from the legacy push-to-talk event path.

Real Gemini verification confirmed visible input/output transcripts, audible
native Japanese responses, multiple consecutive turns in one Cloud session,
and automatic return to listening after playback. The provider session no
longer stops after the first response or loses microphone ownership to a local
session. Native audio remains intelligible but can contain audible seams or
crackle because the current Qt playback owner receives short in-memory WAV
segments. Continuous PCM playback and a future identity-preserving custom
voice remain quality work for the V8 release gate or a separately scoped voice
follow-up; neither weakens the verified V6 session and privacy boundaries.

No hosted-live standalone package was produced in V6. Packaging, packaged
microphone verification, and final audio-quality acceptance remain the V8
release gate.

### Milestone V7: Provider-Neutral Typed Tool Proposals

- [x] Expose only allowlisted action schemas.
- [x] Treat function calls as untrusted `ActionProposal` values.
- [x] Reuse validation, permission, confirmation, execution, and audit.
- [x] Return only sanitized function results.
- [x] Add Gemini Live function proposals behind the provider-neutral adapter.
- [x] Add Ollama tool proposals when the selected local model reports tool-call
  support.
- [x] Fall back to deterministic and JSON proposal paths when a provider model
  does not support native tools.
- [x] Prevent duplicate deterministic and provider execution for one turn.

#### V7A: Explicit Tool Schema Catalog - Complete

V7A adds an SDK-neutral `ProviderActionToolCatalog` derived from the existing
Phase 8 action registry. Provider exposure requires a second explicit list of
action identifiers: registering a future executor does not silently publish it
to Gemini, Ollama, or another intent provider. Unknown, duplicate, and
prohibited actions are rejected while building the catalog.

Exported `ActionToolSchema` values contain only the action identifier,
description, and bounded primitive parameter constraints. They deliberately do
not expose executor identifiers, permission capabilities, repositories,
confirmation state, subprocess handles, or filesystem objects. Schema exposure
does not grant permission and cannot execute an action. The existing bounded
`ActionProposal` and `SanitizedActionResult` voice contracts remain the only
provider-neutral proposal/result values.

V7A verification passed with 1,287 tests and 3 optional-environment skips,
plus repository-wide Ruff, Black, compilation, and diff checks.

V7B translates one provider proposal into one untrusted Phase 8
`ActionRequest`, retains session/turn/proposal ownership, and rejects stale,
duplicate, unknown, or non-ready proposals before the existing validator and
permission service are reached.

#### V7B: Untrusted Proposal Gateway - Complete

V7B adds `ProviderActionProposalGateway` between provider events and the Phase
8 action service. `ActionProposal` now carries both session and turn identity,
so the gateway can use the existing voice-session authority to reject a wrong
session, completed turn, cancelled turn, or replaced turn mechanically. A
bounded replay ledger consumes proposal identities once and rejects duplicate
delivery without retaining target arguments or transcript text.

Only ready proposals whose action identifiers appear in the V7A catalog become
an `ActionRequest`. The request receives a deterministic privacy-safe
correlation identifier and a bounded provider source. Its primitive arguments
remain untrusted and are deliberately left for the unchanged Phase 8
`ActionRequestValidator`; conversion does not validate permissions, request
confirmation, call an executor, or write an action audit entry.

V7B verification passed with 1,294 tests and 3 optional-environment skips,
plus repository-wide Ruff, Black, compilation, and diff checks.

#### V7C: Permission-Gated Dispatch And Sanitized Results - Complete

V7C adds `ProviderActionDispatcher` after the V7B conversion boundary. An
accepted provider request is rechecked against current session/turn authority,
then passes through the unchanged Phase 8 `AssistantActionService` for schema
validation, scoped permission evaluation, confirmation policy, allowlisted
execution, and SQLite audit recording. Provider code receives no service,
permission repository, executor, or confirmation override.

The dispatcher reuses `IntentArbiter` with session-scoped hashed turn and
proposal identities. Provider dispatch waits until local deterministic routing
is complete, and an accepted exact, contextual, or confirmation intent blocks
a conflicting provider proposal for that turn. Replayed conversions cannot
execute twice. Provider actions always enter Phase 8 with `confirmed=False`.
Confirmation-required requests are retained only in a bounded memory-only
store and can be resumed once through a separate trusted local confirmation
call. Denial or confirmation consumes the stored request, stale ownership makes
it non-executable, and explicit `clear()` discards all pending requests. V7D
must call that cleanup hook when the hosted lane stops or changes.

`SanitizedActionResult` now includes session ownership. Provider results expose
only session/turn/proposal identity, a bounded status, and a fixed generic
message. Raw `ActionResult.summary`, metadata, local paths, search matches,
Spotify candidates, credentials, and exception text are never copied into the
provider result. Incorrect action-service correlation or action identity fails
closed. A real SQLite composition test confirms that a provider-origin request
without permission is denied and audited through the Phase 8 repository.

V7C verification passed with 1,307 tests and 3 optional-environment skips,
plus repository-wide Ruff, Black, compilation, and diff checks. At the V7C
boundary, Gemini SDK function declarations and results remained disabled;
V7D performs that provider-transport connection below.

#### V7D: Gemini Live Function Transport - Complete

V7D translates the V7A catalog into Gemini-safe function declarations while
preserving Akiha's dotted action identifiers behind a reversible
transport-only name map. Google SDK objects, raw provider call IDs, and API
session ownership remain inside `GoogleGenAILiveTransport`. Raw call IDs are
hashed into bounded proposal identities before crossing the adapter boundary.
Malformed, unknown, empty, oversized, or non-mapping function calls fail
closed as sanitized protocol errors.

The Gemini adapter reports tool-proposal capability only when an explicit
catalog is configured. It converts transport calls into session- and
turn-owned `ActionProposal` values and accepts only matching
`SanitizedActionResult` values. The hosted worker owns V7B conversion and V7C
dispatch; provider code never receives the action service, executors,
permissions, repositories, or confirmation override. Hosted Live has no
parallel deterministic parser, so the worker explicitly completes the empty
local-routing stage before allowing a provider proposal into arbitration.

Confirmation-required calls remain pending in bounded process memory while a
trusted local Qt dialog shows the validated target. Gemini waits during that
decision and receives only the final generic status and message, matched to
the original SDK function-call ID. Decline, stale ownership, shutdown, lane
change, or worker failure cannot execute the request. Worker shutdown clears
both proposal replay state and pending confirmation arguments.

V7D verification passed with 1,312 tests and 3 optional-environment skips,
plus repository-wide Ruff, Black, compilation, and diff checks. Manual Gemini
tool testing and standalone packaging remain intentionally deferred until V7
and the V8 release gate respectively.

#### V7E: Ollama-Native Tool Proposals - Complete

V7E adds native Ollama tool calling without changing the authority granted to
a local model. The selected model is checked through Ollama's model-details
endpoint and enters the native lane only when it reports the `tools`
capability. That capability result is cached for the lifetime of the selected
provider. Models without it are handed to the existing constrained JSON
proposal path; V7F remains responsible for formal fallback reconciliation and
its complete cross-provider verification.

The Ollama adapter translates only V7A's explicit allowlist into native
function declarations. Transport-safe function names, raw tool-call objects,
assistant tool messages, and Ollama request history remain private to the
adapter. A native call becomes the same bounded `ActionProposal` used by
Gemini, with application-owned session and turn identity supplied by a new
short-lived modular turn authority. Unknown functions, malformed arguments,
unsafe primitive values, excess calls, wrong result ownership, stale turns,
and replayed proposals fail closed before execution.

`OllamaNativeToolThread` owns one non-streaming proposal exchange away from the
Qt event loop. It routes accepted calls through the unchanged V7B gateway,
V7C dispatcher, Phase 8 validation, scoped permission service, trusted local
confirmation dialog, executor, and audit repository. Multiple provider calls
still share one arbitration turn, so at most one can execute. The follow-up
request omits tool declarations to prevent a second action chain, and Ollama
receives only role-tagged generic `SanitizedActionResult` status and message
content. If a native action has begun, a later provider failure is never
retried through another proposal lane.

Plain-text responses from the native decision request and final responses
after an action use the canonical chat persistence path before speech or
subtitle derivatives run. Settings changes replace the native provider slot,
while cancellation and worker cleanup invalidate turn ownership and clear
proposal replay and pending-confirmation state.

V7E verification passed with 1,325 tests and 3 optional-environment skips,
plus repository-wide Ruff, Black, compilation, and diff checks. Real Ollama
model testing and standalone packaging remain intentionally deferred until
the V7 manual roundup and V8 release gate.

#### V7F: Deterministic And Constrained JSON Fallback - Complete

V7F makes fallback ordering and ownership mechanical instead of relying only
on UI control flow. Exact deterministic parsing and ephemeral local context
still run first. A provider fallback turn is opened only after those paths
produce no action and the bounded likelihood gate identifies explicit action
language. The new `ProviderToolFallbackGate` retains only an opaque turn ID,
nonce, and lifecycle state. It permits one JSON request, consumes one result or
failure callback, rejects duplicate or stale delivery, and invalidates all
tokens on provider changes, chat reset, cancellation cleanup, and shutdown.

Compatible Ollama models still use V7E native tools. A model that reports no
`tools` capability, or whose local model-details request fails before any
proposal exists, may hand the same owned turn to the constrained JSON path
once. A native turn that has already proposed or dispatched an action is not
retried through JSON. Hosted text providers without a native adapter enter the
same constrained path directly; no fallback changes the selected provider or
processing location.

The JSON classifier remains default-off and receives only a normalized user
command plus `IntentContextSnapshot` labels. It never receives approved roots,
paths, search results, credentials, file contents, or executor metadata. Its
response must match one exact bounded schema for an allowlisted application,
path-free directory/media search hint, limited Spotify playback control,
fixed clarification topic, or `none`. Unknown actions, invented fields,
unallowlisted applications, path-like values, control characters, oversized
input/output, prose, and malformed JSON fail before action dispatch.

V7F also adds a pre-provider compound-action guard. Requests containing more
than one recognizable desktop action produce a fixed local clarification
instead of letting the model choose one silently. A single title containing a
word such as `and` remains valid when only one clause contains action language.
Accepted direct proposals continue through at-most-once intent arbitration and
the unchanged Phase 8 validation, permission, confirmation, execution, and
audit path. Directory and passive-media hints still require trusted local
resolution beneath approved roots before any target can open.

V7F verification passed with 1,332 tests and 3 optional-environment skips,
plus repository-wide Ruff, Black, compilation, and diff checks. V7G owns the
final source-level provider-tool roundup. Standalone packaging remains deferred
to the V8 release gate.

Ollama officially supports tool calling for compatible models. Its tool calls
remain proposals and receive no additional authority. See
[Ollama tool calling](https://docs.ollama.com/capabilities/tool-calling).

#### V7G: Final Provider-Tool Verification - Complete

V7G adds a cross-layer closure regression over the real Phase 8 SQLite
permission and audit repository. The same provider-neutral proposal path is
exercised with Gemini Live and Ollama-native source identities. A missing grant
is denied and audited without execution; a scoped application grant permits
exactly one registered executor call; replay is rejected; and executor
summaries and metadata remain absent from the provider-safe result. A separate
composition check proves that an accepted deterministic action claim prevents
provider execution before either a side effect or provider-origin audit can
occur.

The closure audit also retains the earlier transport-specific coverage for
Gemini declaration/result ownership, Ollama capability negotiation and native
calls, constrained JSON parsing, confirmation, cancellation, stale ownership,
fallback cleanup, and canonical response persistence. V7G automated
verification passed with 1,361 tests and 3 optional-environment skips, plus
repository-wide Ruff, Black, compilation, and diff checks.

The first real Gemini roundup exposed three closure defects now covered by
regressions. A hosted microphone hard limit no longer destroys the Cloud
session: detected speech is finalized as the current turn, while an entirely
idle capture window renews listening without a provider error. Detached Gemini
tool tasks now consume their result and stop visibly if returning a sanitized
function result fails, so a provider operation cannot strand the UI in
`Hearing cloud transcript`. Finally, Gemini and Ollama may propose an approved
directory by its display name, such as `Downloads folder`; the gateway resolves
that name locally to the approved path before the unchanged Phase 8 validator
and permission policy run. Private path values are not added to provider tool
declarations or provider-visible results.

A second real-microphone pass exposed a false `Listening` state after playback:
each Cloud turn discarded the previous room-noise calibration, so immediate
speech could be absorbed into a new fan-noise baseline and never produce an
endpoint. The Qt capture owner now retains only its scalar noise-floor estimate
in memory across turns, clears it when the selected microphone changes, and
continues adapting it from ambient frames. Idle-window renewal is also queued
until the previous Qt audio source has released capture ownership. No raw audio,
exact level history, or transcript content is retained by this correction.

The final source retest found one microphone-ownership edge case and one
approved-directory usability gap. A duplicate Talk request while Cloud already
owned an active capture could overwrite the capture source before Qt rejected
the second start; the later timeout then followed the wrong local error path.
Active listen requests are now idempotent, duplicate capture starts cannot
replace their owner, and hosted shutdown always issues an idempotent microphone
release even if visible state has already recovered. Provider directory and
passive-file actions may also use root-relative targets such as
`Downloads/Video` or `Downloads/Video/example.mp4`. Resolution stays local,
requires an existing approved root, preserves passive-file confirmation, and
rejects traversal before the unchanged Phase 8 path and permission checks.

Approved file and directory searches now accept the same root-relative
descendant form, such as `Downloads/Video`. Search matches are emitted only to
Akiha's local Qt presentation callback, where the existing bounded results UI
and ephemeral selection context receive at most ten entries. Gemini receives
only the existing generic sanitized action status and never receives filenames,
paths, executor metadata, or raw summaries. The provider tool description
explicitly directs Gemini to the private local-results surface instead of
claiming that approved video search is unavailable.

Provider file search now carries an explicit local result mode. Search-only
requests present matches without opening them; a named play/open request opens
only one unique match through the existing confirmation gate; and an explicit
request for any matching media may select one local result but still requires
confirmation. Voice-spoken media searches may opt into relaxed token matching
only when no exact filename substring exists. This turns a combined title such
as `Leia -Elis-` into two local candidates rather than guessing between the
real `05 Leia.flac` and `01 -ELIS-.flac` files. Multiple candidates remain
ephemeral.

Numbered Cloud follow-ups now use an opaque, local-only bridge. Gemini may call
the existing open-file or open-directory tool with exactly `result 1` through
`result 10`; it never receives the indexed filename or path. The proposal
gateway resolves the index against only the latest bounded local result set,
expires that set after five minutes, and rejects wrong-kind, stale, malformed,
or out-of-range references through normal validation. A resolved passive file
still enters the original path validator, scoped permission policy, extension
policy, and trusted local confirmation. New chat, Clear chat, provider change,
session shutdown, and replacement search results invalidate the old references.

The final Gemini Spotify retest also closed a provider-argument mismatch. A
Cloud proposal that combines `title by artist` into one track field is split
locally, and a slightly damaged artist may trigger one title-only recovery
without lowering the global match threshold. Ambiguous releases and likely
trailing transcription noise are presented locally instead of guessed. Gemini
may select a displayed Spotify candidate only through an opaque `result N`;
the validated track URI and all candidate metadata remain local. Provider
identity rules now prohibit claiming that an action succeeded until its
returned status is successful.

The final source verification completed with repository-wide tests, Ruff,
Black, compilation, and diff checks. The final real Gemini sign-off used this
short result-reference smoke sequence:

1. Ask for a media search that returns at least two local results.
2. Say `Play result 1` and confirm that the local file prompt names result 1.
3. Decline once and confirm that no file opens; repeat and approve once.
4. Request an out-of-range result and confirm that no action executes.
5. Start a new chat, repeat the old result reference, and confirm it is stale.
6. Confirm Cloud listening continues after the action result.

The source-run Gemini Live sign-off passed on 2026-08-13. The user confirmed
approved application launching, Spotify search and playback, approved-root and
descendant directory access, passive local-media opening, continued multi-turn
listening after tool results, and bounded local Spotify suggestions for
ambiguous or imperfectly transcribed track requests. Numbered result selection
remained local and did not expose candidate metadata to Gemini. Automated
coverage retains the equivalent Ollama-native source identity and shared
permission, execution, replay, audit, and sanitized-result boundary; a manual
Ollama-native pass remains optional until a compatible local model is
installed. No standalone candidate was built in V7. All packaged verification
remains owned by V8.

### Milestone V8: Hosted Live Release Gate

- [x] Freeze the clean V7 source baseline and confirm Python 3.13 packaging.
- [x] Require packaged voice and Gemini Live dependencies explicitly.
- [x] Reject environment files, common secret files, private exports, and local
  databases during packaged-artifact validation.
- [x] Run the full automated suite and quality checks.
- [x] Run fresh and existing-data source startup and migration smoke checks.
- [x] Complete the source-run manual Gemini Live and provider-tool roundup.
- [x] Reconcile privacy, security, architecture, build, and smoke documentation.
- [x] Build and validate one Python 3.13 standalone candidate.
- [x] Pass fresh and existing-data automated packaged smoke checks.
- [x] Complete packaged microphone, Gemini, provider tools, local fallback,
  actions, and shutdown smoke tests.
- [x] Retain only the confirmed replacement package.

V8A through V8G completed on 2026-08-13. The Python 3.13.14 gate passed 1,372
tests with three optional-environment skips, dependency checks, Ruff, Black,
compilation, source startup, and fresh/existing-data migration smoke. The V8
standalone contains 193 files (about 393 MB), uses the Windows GUI subsystem,
passes required-asset and private-data validation, starts without a console,
and passes fresh and existing-data packaged smoke with clean logs. The final
incremental candidate linked 1,312 files while preserving the previously
verified Gemini SDK native object. Real-device acceptance confirmed visual UI,
microphone input, immediate Cloud transcript projection, continuous Gemini
Live listening, application and approved-directory actions, Spotify commands,
and graceful Quit. Obsolete candidates, compiler trees, rollback copies, and
smoke data were removed after acceptance; only `dist/nuitka-v8-final` remains.
See `docs/phases/phase-06-packaging/V8_MANUAL_SMOKE_2026-08-13.md` for the
signed-off evidence. This closes the Post-Phase 8 Voice Intelligence roadmap.

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

## Remaining V6-V8 Questions For Reviewers

1. Should provider-native tool calling land only after conversation-only
   Gemini Live sessions pass a separate internal checkpoint inside V6?
2. Are final input/output transcriptions sufficient canonical records for the
   Gemini Live lane?
3. Should an interrupted assistant partial remain session-visible, or be
   removed immediately?
4. Are any diagnostics listed above capable of revealing private content
   indirectly?
5. Which latency budgets should become formal exit criteria after measuring
    the current machine?
6. Does the architecture remain sufficiently provider-neutral for a future
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

## Consolidated V0 Decision And Evidence

V0 evaluated Pipecat 1.6.0 as a possible owner of Akiha's concurrent voice
pipeline. The bounded spike proved that Pipecat could pass text and termination
frames on Windows and Python 3.13, but it did not justify becoming a production
dependency.

The isolated environment occupied roughly 564-600 MB. A minimal text-only
Nuitka probe selected 2,938 modules, ran longer than 20 minutes, produced about
2.7 GB of incomplete standalone output, and never produced a runnable
executable. Source startup also attempted an unnecessary online NLTK language
resource lookup. By comparison, Akiha's existing Qt, memory, voice, actions,
Spotify, and UI package already owned all required product boundaries.

The V0 probes demonstrated that Akiha's existing services could provide:

- one Qt microphone and one Qt playback owner;
- rolling transcript revisions with one authoritative final;
- shared local and hosted text-provider response contracts;
- concurrent VOICEVOX synthesis with canonical playback order;
- typed action validation, permission, execution, and audit isolation; and
- turn-scoped cancellation that rejects late callbacks.

**Accepted decision:** retain Akiha-owned, framework-neutral orchestration. Do
not add Pipecat as a production, development, or packaging dependency. Revisit
only if a future framework proves a materially smaller dependency graph,
offline startup, successful bounded Windows packaging, correct Qt ownership,
typed-action isolation, and a capability Akiha's coordinator cannot reasonably
provide.

The original V0 verification closed with 31 focused pipeline tests, 66 action
gateway tests, 33 Qt playback/controller tests, and a full result of 958 tests
passing with three skipped at that point in project history. The disposable
Pipecat environments, caches, and incomplete package were removed.

## Consolidated V2 Hearing Benchmark

The reproducible V2 benchmark compares cumulative partial recognition with the
bounded rolling adapter at 16 kHz mono PCM, 0.6-second preview cadence, and an
eight-second rolling partial window.

| Utterance | Strategy | STT calls | Audio processed | Largest partial | Final input |
| ---: | --- | ---: | ---: | ---: | ---: |
| 3 s | cumulative | 6 | 12.0 audio-s | 3.0 s | 3.0 s |
| 3 s | rolling | 6 | 12.0 audio-s | 3.0 s | 3.0 s |
| 10 s | cumulative | 17 | 91.6 audio-s | 9.6 s | 10.0 s |
| 10 s | rolling | 17 | 88.6 audio-s | 8.0 s | 10.0 s |
| 30 s | cumulative | 51 | 795.0 audio-s | 30.0 s | 30.0 s |
| 30 s | rolling | 51 | 380.6 audio-s | 8.0 s | 30.0 s |

First-partial eligibility remains 0.6 seconds. Thirty-second utterances reduce
repeated audio submitted to STT by 52.1 percent while final recognition still
receives the complete bounded utterance. Python framing overhead remained
below 4 ms in the deterministic benchmark; actual faster-whisper inference,
speech accuracy, fan noise, and machine load remain hardware-dependent.
