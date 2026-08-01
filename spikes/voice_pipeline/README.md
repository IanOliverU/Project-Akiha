# Voice Pipeline V0 Spike

This directory evaluates the Post-Phase 8 concurrent voice architecture. It is
outside `project_akiha`, is not included by the setuptools package finder, and
must not read or write production configuration, credentials, chat, memory, or
assistant-action data.

The framework-neutral harness proves:

- partial transcripts may prepare replaceable intent state but cannot commit it
- only one authoritative final transcript commits intent
- streamed response sentences can synthesize and play while later text is
  still being generated
- independently synthesized segments still play in canonical order
- cancelled and stale turn callbacks are rejected
- cumulative snapshots from the existing Qt microphone owner become bounded,
  monotonic PCM frames without opening another capture device
- stable response segments use the existing `SpeechOutputService`, synthesize
  concurrently with a strict bound, play in order, and cancel as one turn
- bounded PCM frames feed the existing `SpeechInputService`, emit stabilized
  replaceable partial revisions, and produce one authoritative final revision

The harness is not a production coordinator. It provides a stable behavior
target for comparing Pipecat with an Akiha-owned implementation.

`pipecat_core_probe.py` is a dependency-isolated compatibility check. Run it
only from a temporary environment containing Pipecat; it is not imported by
the application or automated unit suite.

Run its focused tests with:

```powershell
.\.venv313\Scripts\python.exe -m unittest tests.unit.spikes.test_voice_pipeline_spike
```
