# Phase 7 Voice Layer

Phase 7 gives Akiha a local-first voice while keeping speech recognition,
speech synthesis, and character identity independently replaceable. A
temporary Japanese voice is enough to complete this phase; a custom-trained
voice is explicitly deferred.

The phase is divided into two internal checkpoints:

- **Phase 7A: Voice Plumbing** proves that listening, synthesis, playback,
  settings, diagnostics, and visual states work reliably.
- **Phase 7B: Minimal Akiha Voice Identity** makes the spoken wording feel
  intentional and consistent with `docs/AKIHA.MD`.

Phase 7A must pass its own smoke checkpoint before Phase 7B begins. This keeps
technical audio failures separate from subjective character-style tuning.

## Phase Goal

Let the user speak to Akiha through push-to-talk and let Akiha speak responses
through a temporary local Japanese voice, with clear listening, thinking,
speaking, muted, and error states.

## Guiding Principles

- Local-first voice processing is the default.
- Voice is optional and the app must still work when voice is disabled.
- Voice sound and voice identity are separate layers.
- Providers must be replaceable without changing chat or character logic.
- Existing event, mood, presence, and settings systems should be reused.
- Missing microphones, engines, models, and playback devices must not crash the
  companion.
- Microphone use must be visible and controlled by the user.
- Phase 7 does not train or imitate an official game or voice-actor voice.

## Voice Pipeline

```text
Microphone / Push-to-talk
    -> Speech-to-text provider
        -> Existing chat and memory pipeline
            -> AI provider response
                -> Post-response speech style layer
                    -> Text-to-speech provider
                        -> Audio playback
                            -> Speaking state and animation
```

The identity hook is deliberately placed **after the provider response and
before the TTS call**. It may prepare a spoken rendering of the response, but it
must not rewrite the stored assistant message or bypass the existing chat and
memory pipeline.

If speech styling fails or produces unusable text, the voice pipeline falls
back to the original assistant response. A style failure must never turn an
otherwise valid response into silence.

## Temporary Provider Direction

- **Speech-to-text:** start with a local Whisper-compatible provider such as
  `faster-whisper`.
- **Text-to-speech:** start with the local VOICEVOX HTTP engine and a
  user-selected installed Japanese speaker.
- **Future providers:** Kokoro, Piper-compatible engines, cloud services, and a
  properly licensed custom Akiha voice can be added behind the same provider
  interfaces later.

VOICEVOX is a temporary Japanese voice backend, not Akiha's final voice. Phase
7B supplies character identity through wording and delivery guidance so the
temporary sound still belongs to a coherent companion.

## Phase 7A: Voice Plumbing

### Configuration And Contracts

- [x] Define a voice configuration model.
- [x] Persist voice settings in the existing user configuration system.
- [x] Add a `VoiceInputProvider` interface for speech recognition.
- [x] Add a `VoiceOutputProvider` interface for speech synthesis.
- [x] Keep provider-specific code outside UI and core conversation logic.
- [x] Add explicit disabled and unavailable provider states.

Suggested configuration includes:

- Voice enabled.
- Push-to-talk enabled.
- Speech-to-text provider and model.
- Text-to-speech provider, endpoint, and speaker.
- Microphone input device.
- Audio output device.
- Automatic speech for assistant replies.
- Separately opt-in speech for policy-approved proactive check-ins.
- Optional live transcription preview.
- Optional silence endpointing and final-transcript auto-send.
- Playback volume and speaking rate where supported.

### Speech Input

- [x] Add a push-to-talk command surface in the chat window.
- [x] Add start, stop, cancel, and timeout handling for microphone capture.
- [x] Add a local speech-to-text service.
- [x] Add a `faster-whisper` provider adapter.
- [x] Insert accepted transcripts into the existing chat input path.
- [x] Show revisable interim transcription while recording when enabled.
- [x] Stop recording after configurable silence when enabled.
- [x] Auto-send only the authoritative final transcript when enabled.
- [x] Prevent accidental sends for empty or failed transcripts.
- [x] Keep microphone capture off until the user starts push-to-talk.

### Speech Output

- [x] Add a text-to-speech orchestration service.
- [x] Add a VOICEVOX local HTTP provider adapter.
- [x] Add provider health and speaker discovery checks.
- [x] Add audio synthesis and playback support.
- [x] Add stop-speaking and replay controls.
- [x] Prevent overlapping playback unless explicitly supported later.
- [x] Allow automatic speech for assistant replies to be disabled.
- [x] Clean up temporary audio safely after playback.

### State And Companion Integration

- [x] Add voice states for idle, listening, thinking, speaking, muted, and
  error.
- [x] Publish voice state changes through the existing event system.
- [x] Map voice states into the existing mood, presence, and animation flow.
- [x] Restore the previous companion state after listening or speaking ends.
- [x] Ensure voice activity does not fight walking, sleeping, or shutdown
  behavior.

### Settings And Diagnostics

- [x] Add a Voice section to Settings.
- [x] Add input and output device selectors.
- [x] Add provider, endpoint, model, and speaker controls.
- [x] Add a test microphone action.
- [x] Add a test voice action with a short Japanese phrase.
- [x] Show clear diagnostics for a missing backend, unavailable model, missing
  microphone, failed synthesis, and failed playback.
- [x] Log technical voice failures without logging captured audio or unnecessary
  transcript content.

### Automated Coverage

- [x] Test voice configuration defaults, loading, saving, and invalid values.
- [x] Test input and output provider contracts.
- [x] Test unavailable-provider and disabled-voice behavior.
- [x] Test push-to-talk state transitions and cancellation.
- [x] Test synthesis, playback, stop, and cleanup paths.
- [x] Test voice event publication and companion-state restoration.
- [x] Test diagnostics for backend, synthesis, microphone, and playback
  failures.
- [x] Test shutdown while listening, transcribing, synthesizing, and speaking.

Foundation note, 2026-07-29:

- Voice remains disabled by default, so no microphone, model, or HTTP engine is
  accessed during normal startup.
- `VoiceConfig` persists provider choices, devices, automatic reply speech,
  volume, speaking rate, and provider timeout settings through the existing
  TOML configuration store.
- The first provider-neutral contracts cover captured PCM audio, transcripts,
  synthesis requests, synthesized audio, selectable voices, and provider health
  states.
- `VoiceStateMachine` defines idle, listening, thinking, speaking, muted, and
  error transitions without importing Qt.
- Canonical voice request, transcript, state, and error event names are
  registered.
- `VoiceController` is composed into application startup, begins muted when
  voice is disabled, applies updated voice configuration without a restart, and
  publishes privacy-safe state, transcript, and error events.
- Push-to-talk request, stop, and cancel events drive listening and thinking
  state transitions and the bounded microphone-capture lifecycle.
- Speech requests enter synthesis state and expose explicit playback-start,
  stop, error, and recovery transitions for the upcoming TTS service.
- Input transcription and output synthesis retain separate operation ownership,
  so a speech-stop request cannot cancel transcription and a listen-cancel
  request cannot cancel synthesis.
- Chat now exposes a fixed-width push-to-talk control for idle, listening,
  transcription, synthesis, and speaking states. Recognized text is inserted at
  the current input cursor for review unless the user explicitly enables final
  transcript auto-send.
- A framework-free chat voice presenter validates state, transcript, and error
  event payloads before updating Qt controls.
- Qt Multimedia now provides bounded 16 kHz mono PCM microphone capture without
  adding another native audio dependency. The input device is opened only after
  an accepted push-to-talk request.
- Captured PCM stays on a direct callback path and is never published through
  `EventBus`, preventing the event logger from serializing raw microphone data.
- Capture supports explicit stop, cancellation, device errors, empty-capture
  errors, and a configurable timeout. Shutdown always attempts to release the
  microphone and records the cleanup result.
- If the optional STT dependency or model is unavailable, the recording reports
  a visible provider error instead of remaining stuck in the thinking state.
- Local STT now runs through `SpeechInputService` and a dedicated Qt worker, so
  model loading and transcription do not block the UI thread.
- `FasterWhisperProvider` wraps captured PCM in an in-memory WAV stream, uses
  CPU/int8 inference, caches its model under
  `%LOCALAPPDATA%\Akiha\models\faster-whisper\`, and loads both the dependency
  and model lazily.
- Successful transcripts return through the existing editable Chat input path.
  Cancellation discards late provider results instead of inserting them.
- The optional `voice` dependency group installs faster-whisper on Python 3.13.
  Normal Windows Python 3.14 remains a backend-unavailable source environment
  until its native dependency wheels are consistently supported.
- `SpeechOutputService` validates provider health, builds provider-neutral
  synthesis requests, and converts backend failures into stable diagnostics.
- Speech synthesis runs on a dedicated Qt worker and permits only one active
  request. Stop, settings changes, duplicate requests, and shutdown cancel the
  worker and discard any late provider result.
- Encoded synthesized audio stays on a direct playback callback path and is
  never published through `EventBus` or written to technical logs.
- `VoiceVoxProvider` checks `/version`, discovers talk-capable styles through
  `/speakers`, creates an `/audio_query`, applies the configured speaking rate,
  and sends that query to `/synthesis`.
- VOICEVOX uses the configured local endpoint and timeout with no additional
  HTTP dependency. Invalid JSON, malformed speaker data, HTTP failures, empty
  audio, and non-WAV responses become stable provider diagnostics.
- HTTP errors do not echo request URLs because VOICEVOX places spoken text in
  the audio-query URL. The text and generated WAV remain outside application
  events and technical logs.
- `QtAudioPlayback` sends synthesized WAV bytes to `QMediaPlayer` through an
  open in-memory `QBuffer`; no temporary voice file is created.
- `QAudioOutput` applies the configured output device and volume. Playback
  enters speaking state only after Qt reports that audio started, and natural
  end-of-media restores the voice state.
- Manual stop, settings changes, invalid media, device errors, duplicate
  playback, and shutdown all release the in-memory buffer. The application
  shutdown report now verifies playback cleanup independently from synthesis
  worker cleanup.
- Chat exposes a state-aware stop action during synthesis and playback plus an
  icon-only replay action while voice is idle.
- Replay retains only the last text handed to playback and re-enters the normal
  synthesis pipeline. It never retains the generated WAV, is unavailable while
  another voice operation is active, and is cleared with New Chat or Clear
  Chat.
- Technical event logging now redacts both speech-request text and recognized
  transcript text while retaining non-content metadata such as request source
  and detected language.
- `AssistantSpeechController` receives the exact assistant response only after
  streaming, persistence, and memory processing complete. It requests speech
  only when automatic speech is enabled, output is configured, and voice is
  idle.
- Automatic assistant speech remains disabled by default and updates live from
  saved configuration. Cancelled, failed, empty, or voice-conflicting responses
  do not enter synthesis.
- Chat display and persisted conversation text remain unchanged. Phase 7B can
  later style a temporary copy after this completion boundary and before TTS.
- Settings now exposes a dedicated Voice tab with a live master switch,
  push-to-talk and automatic-reply switches, provider configuration, editable
  device selectors, speaker ID, volume, speaking rate, and timeout controls.
- Proactive speech has its own default-off setting. It subscribes only to
  successful proactive-delivery events, so behavior policy, quiet hours,
  cooldowns, delivery availability, and voice-busy checks remain authoritative.
- Live dictation is an opt-in semi-real-time layer around faster-whisper.
  Periodic in-memory snapshots produce revisable `Hearing:` text while a
  coalescing queue prevents concurrent model work.
- Optional local signal-energy endpointing stops capture after speech followed
  by configurable silence. Manual Stop remains available in noisy rooms.
- Interim guesses are never added to the message input, sent to the AI
  provider, persisted, or logged verbatim. Capture completion runs one final
  transcription pass; only that result can enter the normal chat submission
  path.
- Voice Settings now includes provider health, microphone, and Japanese output
  tests. The microphone test uses the real capture and faster-whisper pipeline
  but discards recognized words and publishes only non-content success
  metadata. The output test uses the configured VOICEVOX speaker, playback
  device, volume, and speaking rate.
- Provider health checks run off the Qt UI thread and report STT and TTS status
  independently. Missing dependencies, unavailable VOICEVOX, capture failures,
  synthesis failures, and playback failures remain recoverable.
- Saving Voice settings applies them immediately and persists them for future
  launches. Voice remains opt-in for fresh installs because its local STT and
  TTS backends may not be present.
- Recoverable microphone, transcription, synthesis, and playback failures now
  publish a visible error diagnostic and transient error state before returning
  voice to idle. One failed operation no longer disables automatic speech or
  push-to-talk for the rest of the session.
- Chat now shows explicit microphone-ready, listening, and transcribing states.
  A successful transcript appears in a non-persistent `Heard:` preview and is
  inserted into the editable message field for review by default. An explicit
  auto-send setting can submit the final transcript instead.
- Voice states now temporarily overlay the underlying companion mood. Listening,
  thinking, speaking, muted, and error states receive distinct presence text and
  pet visual cues; returning to idle restores the latest activity-driven mood.
  Mood-driven sleep may wake for active voice work, while manual sleep and
  walking remain under user control.

### Phase 7A Smoke Checkpoint

- [x] Source app starts normally with no voice backend installed.
- [ ] Voice can be enabled and disabled without restarting the app.
- [x] Push-to-talk captures a short phrase and places the transcript in chat.
- [x] A temporary Japanese TTS phrase can be synthesized and played when
  VOICEVOX is available.
- [x] Missing backend and audio-device failures are visible but do not crash the
  app.
- [x] Listening, thinking, and speaking states appear and return to the prior
  companion state.
- [x] Stop-speaking and app Quit end audio work without hanging.
- [x] Unit tests, Ruff, Black, and source smoke pass.

Phase 7A manual checkpoint completed on 2026-07-30. Provider setup,
microphone recognition, Japanese voice output, mood cues, presence changes,
and companion-state restoration were confirmed in the running application.

Phase 7A is done only when the voice system works technically and passes this
checkpoint. The output may still sound generic at this point.

## Phase 7B: Minimal Akiha Voice Identity

### Identity Profile

- [x] Create a small runtime speech identity profile derived from
  `docs/AKIHA.MD`.
- [x] Keep identity rules independent from STT and TTS providers.
- [x] Define rules for normal conversation, concern, reminders, errors, and
  proactive check-ins.
- [x] Add a compact set of original sample phrases for manual testing.
- [x] Do not copy official dialogue or train against game voice clips in this
  phase.

Minimum spoken character direction:

- Formal, polite, refined, and precise.
- Composed and confident without sounding emotionless.
- Direct and occasionally strict, but not cruel.
- Caring through concern, responsibility, and practical guidance.
- Reserved in affection rather than overly romantic or familiar.
- More likely to express worry through a reminder than through exaggerated
  reassurance.

Avoid:

- Slang and meme language.
- Excessive cheerfulness or childish delivery.
- Loud or violent comedy-tsundere behavior.
- Constant scolding, jealousy, or possessiveness.
- Overly ornate language that sounds unnatural when spoken.
- Direct copies of official Akiha lines.

### Style Layer

- [x] Add a lightweight speech style service after provider response generation
  and before TTS synthesis.
- [x] Preserve the original assistant message for chat display and persistence.
- [x] Produce a separate spoken-text value when speech-specific adjustment is
  needed.
- [x] Keep factual meaning, names, numbers, and safety-critical content intact.
- [x] Avoid repeatedly transforming already styled text.
- [x] Fall back to the raw assistant response when styling fails, returns empty
  text, or produces malformed output.
- [x] Log style fallback without exposing unnecessary conversation content.

### Mood And Delivery

- [x] Let the current mood influence restraint, concern, and speaking pace where
  the selected TTS provider supports it.
- [x] Add original spoken lines for idle check-ins, self-care reminders,
  settings tests, and recoverable errors.
- [x] Keep proactive speech behind the existing notification policy and
  cooldowns.
- [x] Ensure muted or quiet-hour behavior prevents unsolicited playback.

### Verification

- [x] Test style rules for representative assistant responses.
- [x] Test that displayed and stored chat text remains unchanged.
- [x] Test raw-text fallback for exceptions, empty output, and malformed output.
- [x] Test that style processing cannot block TTS playback indefinitely.
- [ ] Complete a manual listening pass across normal, concerned, strict,
  proactive, and error scenarios.

### Optional English Subtitles

- [x] Add a default-off `Show English subtitles` Voice setting.
- [x] Translate completed Japanese assistant responses through the currently
  selected AI provider without delaying TTS playback.
- [x] Display English as a visually separate, non-canonical subtitle.
- [x] Preserve the original Japanese response for chat persistence, memory,
  context assembly, and speech.
- [x] Cancel or discard late subtitle work when the setting is disabled, chat
  is cleared, a new chat starts, the provider changes, or the app exits.
- [x] Fall back to the original Japanese response when translation fails or
  returns unusable text.
- [x] Avoid logging the source response or provider error details.
- [ ] Persist successful subtitles across application restarts.
- [ ] Define and implement translated transcript export behavior.

### Phase 7B Done Criteria

- [x] Spoken text uses the style layer before TTS while displayed chat remains
  unchanged.
- [ ] The temporary voice consistently uses the minimum Akiha character
  direction.
- [x] Style failures fall back to safe raw text and do not cause silent
  responses.
- [x] Provider replacement does not require changes to identity rules.
- [ ] Manual listening confirms the result feels at least directionally
  Akiha-like.
- [ ] Unit tests, Ruff, Black, source smoke, and the Phase 7 manual smoke pass.

## Manual Phase 7 Smoke

- [ ] Start the source app with voice disabled and no voice dependencies.
- [ ] Open Voice settings, save changes, and restart the app.
- [ ] Run Check setup and confirm both provider results are visible.
- [ ] Run Test microphone, speak briefly, stop, and confirm the pass result.
- [ ] Run Test voice and hear the short Japanese phrase.
- [ ] Verify microphone use starts only after push-to-talk.
- [ ] Speak a Japanese phrase and an English phrase through push-to-talk.
- [ ] Edit a transcript before sending it.
- [ ] Enable live transcription and confirm `Hearing:` text revises while
  speaking.
- [ ] Enable silence endpointing and confirm a pause stops the recording.
- [ ] Enable final-transcript auto-send and confirm interim text is never sent.
- [ ] Generate a mock-provider response and hear it through VOICEVOX.
- [ ] Enable English subtitles with a non-mock AI provider and confirm a
  separate English line appears without delaying Japanese speech.
- [ ] Stop or fail a translation request and confirm the Japanese response
  remains intact.
- [ ] Stop playback and start another response.
- [ ] Disable automatic speech and confirm chat still works.
- [ ] Stop VOICEVOX and confirm the app reports the failure without crashing.
- [ ] Confirm listening, thinking, speaking, muted, and error states.
- [ ] Confirm quiet hours and mute prevent unsolicited speech.
- [ ] Quit while listening and while speaking; confirm the process exits cleanly.
- [ ] Re-run relevant packaged smoke with all voice providers treated as
  optional dependencies.

## Privacy And Safety

- Microphone recording is push-to-talk only in Phase 7.
- No always-listening wake word is added.
- Raw microphone recordings are temporary and are not retained by default.
- Interim transcripts remain display-only. Final transcripts follow the
  existing conversation and memory controls after manual Send or after the user
  explicitly enables auto-send.
- Voice diagnostics avoid recording raw audio or unnecessary transcript text.
- Cloud STT and TTS providers are outside the initial Phase 7 scope.
- Custom voice training and public-distribution rights require a separate future
  decision.

## Out Of Scope

- Always-listening wake words.
- Autonomous background recording.
- Cloud voice providers.
- Emotion recognition from the user's voice.
- Full Japanese linguistic rewriting or honorific relationship modeling.
- Detailed phoneme, accent, and prosody authoring.
- Training or cloning Akiha's official game voice.
- Live2D lip sync and advanced mouth animation.
- Phase 8 pet statistics and care-loop mechanics.

## Exit Criteria

Phase 7 is complete when:

- Phase 7A passes its technical checkpoint independently.
- Phase 7B passes its identity and fallback checks.
- Akiha can accept push-to-talk input and speak through a temporary local
  Japanese voice.
- Voice remains optional, local-first, diagnosable, and replaceable.
- Listening, thinking, speaking, muted, and error states integrate with the
  existing companion experience.
- Shutdown, privacy, and failure paths are verified.
- The roadmap and user documentation match the implemented behavior.
