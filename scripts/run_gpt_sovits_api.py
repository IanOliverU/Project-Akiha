"""Launch the official GPT-SoVITS API with Windows FFmpeg DLL support."""

from __future__ import annotations

import os
import runpy
from pathlib import Path

_ffmpeg_dll_directory = None


def _install_wav_loader_compatibility() -> None:
    """Use SoundFile for WAV references when TorchCodec lacks FFmpeg access."""
    import soundfile
    import torch
    import torchaudio

    def load_wav(
        filepath: object,
        *args: object,
        **kwargs: object,
    ) -> tuple[torch.Tensor, int]:
        del args
        channels_first = bool(kwargs.pop("channels_first", True))
        data, sample_rate = soundfile.read(
            filepath,
            dtype="float32",
            always_2d=True,
        )
        audio = torch.from_numpy(data)
        if channels_first:
            audio = audio.transpose(0, 1)
        return audio, int(sample_rate)

    torchaudio.load = load_wav


def main() -> None:
    global _ffmpeg_dll_directory
    ffmpeg_bin = os.environ.get("AKIHA_FFMPEG_BIN", "").strip()
    if os.name == "nt" and ffmpeg_bin:
        try:
            _ffmpeg_dll_directory = os.add_dll_directory(ffmpeg_bin)
        except OSError:
            # PATH-based DLL discovery remains available on Windows even
            # when a protected per-user WinGet directory rejects this API.
            _ffmpeg_dll_directory = None

    _install_wav_loader_compatibility()
    api_path = Path.cwd() / "api_v2.py"
    if not api_path.is_file():
        raise FileNotFoundError(f"GPT-SoVITS API entry point is missing: {api_path}")
    runpy.run_path(str(api_path), run_name="__main__")


if __name__ == "__main__":
    main()
