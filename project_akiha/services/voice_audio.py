"""Small audio helpers used while preparing local voice reference data."""

from __future__ import annotations

import math
import wave
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np


def _read_pcm_wav(path: Path) -> tuple[int, np.ndarray]:
    np = _numpy()
    with wave.open(str(path), "rb") as source:
        if source.getnchannels() != 1 or source.getcomptype() != "NONE":
            raise ValueError("Only uncompressed mono WAV files are supported.")
        sample_rate = source.getframerate()
        sample_width = source.getsampwidth()
        raw = source.readframes(source.getnframes())

    if sample_width == 1:
        samples = (
            np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0
        ) / 128.0
    elif sample_width == 2:
        samples = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    elif sample_width == 3:
        packed = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3)
        values = (
            packed[:, 0].astype(np.int32)
            | (packed[:, 1].astype(np.int32) << 8)
            | (packed[:, 2].astype(np.int32) << 16)
        )
        values = np.where(values & 0x800000, values - 0x1000000, values)
        samples = values.astype(np.float32) / 8388608.0
    elif sample_width == 4:
        samples = np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2147483648.0
    else:
        raise ValueError("Unsupported PCM sample width.")
    return sample_rate, samples


def _trim_silence(
    samples: np.ndarray,
    sample_rate: int,
) -> tuple[np.ndarray, float, float, float]:
    np = _numpy()
    frame_size = max(1, int(sample_rate * 0.02))
    frame_count = max(1, math.ceil(len(samples) / frame_size))
    rms = np.empty(frame_count, dtype=np.float32)
    for index in range(frame_count):
        frame = samples[index * frame_size : (index + 1) * frame_size]
        rms[index] = np.sqrt(np.mean(frame * frame) + 1e-12)
    threshold = max(0.008, float(np.percentile(rms, 10)) * 2.5)
    active = rms > threshold
    if not active.any():
        return np.empty(0, dtype=np.float32), 0.0, 0.0, 0.0
    first = int(np.argmax(active)) * frame_size
    last = min(len(samples), (int(np.where(active)[0][-1]) + 1) * frame_size)
    padding_before = int(sample_rate * 0.06)
    padding_after = int(sample_rate * 0.10)
    start = max(0, first - padding_before)
    end = min(len(samples), last + padding_after)
    return (
        samples[start:end],
        float(active.mean()),
        first / sample_rate,
        (len(samples) - last) / sample_rate,
    )


def _resample(samples: np.ndarray, source_rate: int, target_rate: int) -> np.ndarray:
    np = _numpy()
    if source_rate == target_rate or len(samples) < 2:
        return samples.astype(np.float32, copy=False)
    target_length = max(1, round(len(samples) * target_rate / source_rate))
    source_positions = np.arange(len(samples), dtype=np.float32)
    target_positions = np.linspace(0, len(samples) - 1, target_length)
    return np.interp(target_positions, source_positions, samples).astype(
        np.float32,
        copy=False,
    )


def _numpy():
    try:
        import numpy
    except ImportError as error:
        raise RuntimeError(
            "NumPy is required for local voice data preparation."
        ) from error
    return numpy
