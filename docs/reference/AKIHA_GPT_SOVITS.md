# GPT-SoVITS integration

GPT-SoVITS is the production local voice backend for Akiha.

## Project integration

`project_akiha/providers/voice/gpt_sovits.py` is a provider-neutral HTTP
client. It accepts text from any configured LLM and returns WAV audio. The
client does not own the LLM, microphone, playback device, or conversation
state.

`project_akiha/services/gpt_sovits_engine_manager.py` manages the official
local API process. It discovers the isolated runtime, starts `api_v2.py` on
the configured loopback URL, reports readiness, and shuts down only a process
started by Project Akiha.

The desktop GPT-SoVITS UI does not need to remain open. On Windows,
`scripts/run_gpt_sovits_api.py` supplies the local FFmpeg/DLL environment and
uses SoundFile for WAV reference loading when TorchCodec cannot access a
protected FFmpeg installation.

## Runtime layout

```text
.gpt-sovits-venv/   isolated Python 3.10 runtime
.gpt-sovits-src/    official GPT-SoVITS source and local model files
```

The runtime directories are ignored and are not part of the application
source or standalone distribution. A packaged Akiha build contains only the
small launcher helper. It discovers the separately installed runtime in this
order:

1. Explicit environment overrides.
2. The packaged application directory and up to four parent directories. This
   supports development candidates under `dist/<candidate>/main.dist` without
   copying the multi-gigabyte runtime into every build.
3. `%LOCALAPPDATA%/Akiha/runtimes/gpt-sovits/`.

Optional environment overrides are available:

```text
AKIHA_GPT_SOVITS_ROOT
AKIHA_GPT_SOVITS_SOURCE
AKIHA_GPT_SOVITS_PYTHON
AKIHA_GPT_SOVITS_LAUNCHER
```

The source, Python runtime, and launcher must all resolve to existing local
files before automatic startup is allowed. Missing external runtime files are
reported as unavailable and are never downloaded implicitly.

## Reference data

The original `AKIHA VOICE/` WAV files remain unchanged and ignored. The
dataset builder writes only derived files to:

```text
artifacts/voice/gpt-sovits/akiha-dataset/
```

The application selects a valid 3–10 second derived reference clip and its
matching transcript automatically. The transcript must describe that exact
reference clip.

## Diagnostics and failure behavior

Voice diagnostics check both transcription and GPT-SoVITS availability. A
normal GPT-SoVITS `GET /` 404 is treated as healthy because the official API
does not register a root route; `/openapi.json` is used for process readiness.
Synthesis errors preserve the assistant text on screen and do not expose
spoken response contents in diagnostic messages.

## Performance and consistency

The model stays warm in one managed process. Deterministic text-derived seeds,
a stable reference/transcript pair, bounded CPU synthesis, and ordered audio
playback prioritize consistent Akiha identity over maximum expressive
variation. CPU generation remains slower than GPU generation.
