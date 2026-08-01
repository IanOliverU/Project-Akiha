# Voice Pipeline V0 Evaluation

**Status:** In progress - framework-neutral and Pipecat core probes complete

**Evaluation date:** 2026-08-01

Architecture: `docs/VOICE_INTENT_LIVE_CONVERSATION.md`

## Purpose

This bounded Post-Phase 8 spike determines whether Project Akiha should adopt
Pipecat, adopt selected Pipecat components, or retain Akiha-owned orchestration.
It does not alter the production runtime or read production user data.

## Completed Evidence

- [x] Added a non-packaged framework-neutral pipeline harness under
  `spikes/voice_pipeline/`.
- [x] Proved partial transcripts can prepare intent while only the final
  transcript commits it.
- [x] Proved the first stable sentence can play before provider generation
  finishes.
- [x] Proved independently synthesized segments retain canonical playback
  order.
- [x] Proved cancelled and completed turns reject late callbacks.
- [x] Proved existing local and hosted `AIProvider` implementations share one
  response adapter.
- [x] Installed Pipecat 1.6.0 in an isolated temporary Python 3.13.14
  environment without changing Akiha's `.venv313`.
- [x] Passed text and termination frames through Pipecat's current
  `PipelineWorker` and `WorkerRunner` APIs.
- [x] Prototyped a non-owning Qt snapshot bridge that emits bounded incremental
  PCM frames and rejects duplicate, backwards, mutated, or format-changing
  snapshot streams.
- [x] Prototyped an ordered VOICEVOX segment processor through the existing
  `SpeechOutputService`, including bounded concurrent synthesis, canonical
  playback order, failure cleanup, and per-turn cancellation.

## Measurements

The isolated Pipecat environment measured:

| Measurement | Result |
| --- | ---: |
| Python | 3.13.14 |
| Pipecat | 1.6.0 |
| Environment size | 564,449,640 bytes |
| Site-packages size | 562,163,549 bytes |
| Installed distributions | 56 |
| Warm local `import pipecat` process | about 317 ms |

The environment size is not a predicted standalone-build delta. Some
dependencies overlap Akiha's current voice stack, and Nuitka includes only the
reachable module graph. It is still large enough that full adoption requires a
real packaged-size probe before approval.

## Findings

1. Pipecat's core pipeline is technically compatible with the current Windows
   and Python 3.13 runtime.
2. Current non-deprecated worker APIs function in the isolated probe.
3. Base import attempted to retrieve NLTK `punkt_tab` data when network access
   was unavailable. Offline startup behavior and resource bundling require
   investigation before production use.
4. Pipecat's declared base dependencies include NumPy, Numba, ONNX Runtime,
   OpenAI, NLTK, and related packages. This is a meaningful dependency and
   packaging commitment.
5. Pipecat's standard local Whisper path remains segment-oriented. Akiha still
   needs its rolling recognizer or a proven true-streaming local recognizer for
   partial text during speech.
6. The existing Qt microphone can remain the sole hardware owner. Its current
   cumulative snapshots can be adapted safely, although a direct bounded-frame
   callback will avoid repeated prefix comparison in production.
7. VOICEVOX segment orchestration fits Akiha's existing service contract. The
   remaining output work is adapting ordered segments to the Qt playback owner.
8. Chat, memory, identity, subtitles, typed actions, permissions, and audit
   history remain Akiha-owned regardless of the framework decision.

## Current Decision

**Do not add Pipecat to production dependencies yet.** Continue the bounded V0
evaluation. Pipecat is viable enough to test at the bridge level, but the
dependency footprint, offline import behavior, Qt ownership, VOICEVOX adapter,
and Nuitka result remain unresolved.

## Remaining V0 Checks

- [x] Prototype a Qt audio-frame bridge without opening a second microphone.
- [x] Prototype an ordered VOICEVOX frame processor using fake audio output.
- [ ] Confirm rolling transcript revisions can enter the pipeline without
  relying on Pipecat's segmented Whisper service.
- [ ] Pass a fake typed action proposal through Akiha's real validator/gateway
  boundary without exposing an executor to the provider side.
- [ ] Test cancellation and shutdown through the Pipecat bridge prototypes.
- [ ] Run a minimal Nuitka build and measure artifact size/startup behavior.
- [ ] Record the final adopt, partial-adopt, or do-not-adopt decision.

## Verification

Current repository verification:

- 16 focused pipeline and local/hosted provider tests passed.
- Full suite after the VOICEVOX processor: 943 tests passed, 3 skipped.
- Ruff, Black, and `git diff --check` passed.
- Setuptools package discovery returned 17 `project_akiha*` packages and
  excluded `spikes`.
- The 564 MB temporary Pipecat environment was removed after measurement.

```powershell
.\.venv313\Scripts\python.exe -m unittest tests.unit.spikes.test_voice_pipeline_spike
.\.venv313\Scripts\python.exe -m ruff check spikes tests\unit\spikes
.\.venv313\Scripts\python.exe -m black --check spikes tests\unit\spikes
```

The Pipecat probe is run only from an isolated temporary environment:

```powershell
python spikes\voice_pipeline\pipecat_core_probe.py
```
