# V2 Local Hearing Benchmark

**Date:** 2026-08-01  
**Status:** Complete  
**Command:**
`.venv313\Scripts\python.exe scripts/benchmark_voice_recognition.py --repeats 15`

## Purpose

This benchmark compares the previous cumulative-snapshot STT workload with
the production V2 bounded rolling adapter. It answers whether rolling windows
reduce repeated audio processing without changing first-partial cadence or the
authoritative final recording.

## Method

The benchmark runs the production `CumulativeAudioFrameBridge`,
`RollingAudioBuffer`, and `RollingFasterWhisperAdapter` against a deterministic
fake STT provider. Audio uses the production capture format: 16 kHz, mono,
16-bit PCM. Live snapshots arrive every 0.6 seconds, rolling partials retain at
most 8 seconds, and final recognition receives the bounded complete utterance.

Fifteen repetitions measure Python orchestration time. Audio-seconds submitted
to STT are the primary inference-work proxy because the fake provider does no
model computation.

## Results

| Utterance | Strategy | STT calls | Audio processed | Largest partial | Final input | Median Python overhead |
| ---: | --- | ---: | ---: | ---: | ---: | ---: |
| 3 s | cumulative | 6 | 12.0 audio-s | 3.0 s | 3.0 s | 0.01 ms |
| 3 s | rolling | 6 | 12.0 audio-s | 3.0 s | 3.0 s | 0.37 ms |
| 3 s | rolling reduction | - | 0.0% | - | - | - |
| 10 s | cumulative | 17 | 91.6 audio-s | 9.6 s | 10.0 s | 0.02 ms |
| 10 s | rolling | 17 | 88.6 audio-s | 8.0 s | 10.0 s | 1.00 ms |
| 10 s | rolling reduction | - | 3.3% | - | - | - |
| 30 s | cumulative | 51 | 795.0 audio-s | 30.0 s | 30.0 s | 0.07 ms |
| 30 s | rolling | 51 | 380.6 audio-s | 8.0 s | 30.0 s | 3.32 ms |
| 30 s | rolling reduction | - | 52.1% | - | - | - |

## Conclusions

- Time to the first eligible partial remains 0.6 seconds in both strategies.
- Short commands remain unchanged because they fit inside the rolling window.
- At 30 seconds, rolling recognition reduces the audio submitted to STT by
  52.1 percent and caps each partial request at 8 seconds.
- Final recognition still receives the same bounded complete utterance, so V2
  does not trade final context for lower partial cost.
- Python framing and buffer overhead remains below 4 ms at 30 seconds in this
  deterministic run. Real faster-whisper inference dominates that overhead.
- Peak final-recognition input remains 30 seconds; V2 reduces repeated work,
  not the configured maximum final utterance.

## Limitations

This is not a speech-accuracy or real-time-factor benchmark. A controlled
English/Japanese voice corpus and the user's actual CPU are required to compare
word accuracy, fan-noise behavior, model inference latency, and memory under a
loaded faster-whisper model. Existing endpoint and command regressions remain
the automated proxy until that optional manual corpus exists.

The benchmark is reproducible and tested, so future recognizers can be
compared against the same workload without changing the production interface.
