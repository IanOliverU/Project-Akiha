# Akiha local voice

Project Akiha uses GPT-SoVITS as its permanent local Akiha voice backend.
The voice provider is independent from the AI provider:

```text
LLM response -> text -> Akiha voice service -> local GPT-SoVITS -> WAV playback
```

## Reference recordings

`AKIHA VOICE/` is read-only reference material and is excluded from Git. The
recordings are suitable for few-shot reference conditioning, but are not a
fully labeled corpus for reliable from-scratch TTS training. The application
uses derived files under `artifacts/voice/` and never modifies the source WAVs.

## Default configuration

The default output provider is `gpt-sovits` at:

```text
http://127.0.0.1:9880
```

Project Akiha automatically starts the isolated GPT-SoVITS API when the local
voice system is enabled and stops only the process it started during shutdown.
An externally started API process is detected but never terminated by Akiha.

## Runtime installation

The GPT-SoVITS runtime is intentionally isolated from the main Python
environment:

```text
.gpt-sovits-venv/
.gpt-sovits-src/
```

The manager launches the official `api_v2.py` entry point directly. The
GPT-SoVITS desktop UI does not need to remain open.

## Dataset preparation

The preparation script derives normalized 32 kHz mono WAV files, metadata, and
the GPT-SoVITS training list:

```powershell
python scripts/prepare_akiha_gpt_sovits.py --auto-transcribe
```

Automatic transcripts are drafts and should be reviewed before any future
fine-tuning. Generated data remains under ignored `artifacts/voice/`.

## Performance

CPU inference is fully local but can take several seconds per speech segment.
The application keeps the model process warm, bounds concurrent synthesis to
avoid CPU contention, uses deterministic seeds, and reuses the prepared
reference/transcript pair for consistent speaker identity. An NVIDIA GPU is
the main path for substantially lower latency.

The extracted recordings and resulting voice identity may have copyright,
performer, or distribution restrictions independent of GPT-SoVITS's license.
