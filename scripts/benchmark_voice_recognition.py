"""Compare cumulative and bounded rolling local-STT orchestration."""

from __future__ import annotations

import argparse
import asyncio
import statistics
import time
from dataclasses import dataclass

from project_akiha.app.voice_audio_bridge import CumulativeAudioFrameBridge
from project_akiha.core.voice_session import EndpointReason, VoiceCancellationToken
from project_akiha.providers.voice import (
    CapturedAudio,
    VoiceProviderHealth,
    VoiceProviderStatus,
    VoiceTranscript,
)
from project_akiha.services.rolling_speech_input import (
    RollingFasterWhisperAdapter,
)
from project_akiha.services.speech_input import SpeechInputService

_SAMPLE_RATE_HZ = 16_000
_CHANNELS = 1
_SAMPLE_WIDTH_BYTES = 2
_BYTES_PER_SECOND = _SAMPLE_RATE_HZ * _CHANNELS * _SAMPLE_WIDTH_BYTES
_PARTIAL_INTERVAL_SECONDS = 0.6
_PARTIAL_WINDOW_SECONDS = 8.0
_MAXIMUM_UTTERANCE_SECONDS = 30.0


@dataclass(frozen=True, slots=True)
class StrategyMeasurement:
    """Deterministic STT workload plus measured Python orchestration time."""

    strategy: str
    utterance_seconds: float
    request_count: int
    processed_audio_seconds: float
    first_partial_audio_seconds: float
    maximum_partial_audio_seconds: float
    final_audio_seconds: float
    median_orchestration_ms: float


@dataclass(frozen=True, slots=True)
class BenchmarkComparison:
    """Legacy and rolling measurements for one utterance duration."""

    legacy: StrategyMeasurement
    rolling: StrategyMeasurement

    @property
    def processed_audio_reduction_percent(self) -> float:
        baseline = self.legacy.processed_audio_seconds
        return 100.0 * (baseline - self.rolling.processed_audio_seconds) / baseline


async def benchmark(
    durations: tuple[float, ...] = (3.0, 10.0, 30.0),
    *,
    repeats: int = 15,
) -> tuple[BenchmarkComparison, ...]:
    """Measure deterministic workloads through both recognition strategies."""
    if repeats <= 0:
        raise ValueError("Benchmark repeat count must be positive.")
    comparisons = []
    for duration in durations:
        if not 0 < duration <= _MAXIMUM_UTTERANCE_SECONDS:
            raise ValueError("Benchmark duration must be between zero and 30 seconds.")
        snapshots = _cumulative_snapshots(duration)
        legacy = await _measure_legacy(duration, snapshots, repeats)
        rolling = await _measure_rolling(duration, snapshots, repeats)
        comparisons.append(BenchmarkComparison(legacy=legacy, rolling=rolling))
    return tuple(comparisons)


async def _measure_legacy(
    duration: float,
    snapshots: tuple[CapturedAudio, ...],
    repeats: int,
) -> StrategyMeasurement:
    elapsed = []
    reference_lengths: tuple[int, ...] = ()
    for _ in range(repeats):
        provider = _RecordingProvider()
        service = SpeechInputService(provider)
        started = time.perf_counter()
        for snapshot in snapshots[:-1]:
            await service.transcribe(snapshot)
        await service.transcribe(snapshots[-1])
        elapsed.append(time.perf_counter() - started)
        reference_lengths = tuple(provider.audio_lengths)
    return _measurement("cumulative", duration, reference_lengths, elapsed)


async def _measure_rolling(
    duration: float,
    snapshots: tuple[CapturedAudio, ...],
    repeats: int,
) -> StrategyMeasurement:
    elapsed = []
    reference_lengths: tuple[int, ...] = ()
    for _ in range(repeats):
        provider = _RecordingProvider()
        adapter = RollingFasterWhisperAdapter(
            SpeechInputService(provider),
            partial_interval_seconds=_PARTIAL_INTERVAL_SECONDS,
            partial_window_seconds=_PARTIAL_WINDOW_SECONDS,
            maximum_utterance_seconds=_MAXIMUM_UTTERANCE_SECONDS,
        )
        token = VoiceCancellationToken()
        adapter.start_turn(
            session_id="benchmark-session",
            turn_id="1",
            cancellation_token=token,
            language="auto",
        )
        bridge = CumulativeAudioFrameBridge()
        bridge.start_turn(session_id="benchmark-session", turn_id="1")

        started = time.perf_counter()
        for snapshot in snapshots:
            for frame in bridge.accept_snapshot(snapshot):
                await adapter.accept_audio(frame)
        await adapter.finalize(EndpointReason.MANUAL_STOP)
        elapsed.append(time.perf_counter() - started)
        reference_lengths = tuple(provider.audio_lengths)
        bridge.release()
    return _measurement("rolling", duration, reference_lengths, elapsed)


def _measurement(
    strategy: str,
    duration: float,
    audio_lengths: tuple[int, ...],
    elapsed: list[float],
) -> StrategyMeasurement:
    partial_lengths = audio_lengths[:-1]
    return StrategyMeasurement(
        strategy=strategy,
        utterance_seconds=duration,
        request_count=len(audio_lengths),
        processed_audio_seconds=sum(audio_lengths) / _BYTES_PER_SECOND,
        first_partial_audio_seconds=(partial_lengths[0] / _BYTES_PER_SECOND),
        maximum_partial_audio_seconds=(max(partial_lengths) / _BYTES_PER_SECOND),
        final_audio_seconds=audio_lengths[-1] / _BYTES_PER_SECOND,
        median_orchestration_ms=statistics.median(elapsed) * 1_000,
    )


def _cumulative_snapshots(duration: float) -> tuple[CapturedAudio, ...]:
    snapshot_seconds = []
    current = _PARTIAL_INTERVAL_SECONDS
    while current <= duration + 1e-9:
        snapshot_seconds.append(current)
        current += _PARTIAL_INTERVAL_SECONDS
    # The final capture callback submits the complete recording even when the
    # live cadence emitted an equal-length snapshot immediately beforehand.
    snapshot_seconds.append(duration)
    return tuple(
        CapturedAudio(
            data=bytes(round(seconds * _BYTES_PER_SECOND)),
            sample_rate_hz=_SAMPLE_RATE_HZ,
            channels=_CHANNELS,
            sample_width_bytes=_SAMPLE_WIDTH_BYTES,
        )
        for seconds in snapshot_seconds
    )


class _RecordingProvider:
    def __init__(self) -> None:
        self.audio_lengths: list[int] = []

    async def health(self) -> VoiceProviderHealth:
        return VoiceProviderHealth(VoiceProviderStatus.AVAILABLE)

    async def transcribe(self, audio: CapturedAudio) -> VoiceTranscript:
        self.audio_lengths.append(len(audio.data))
        return VoiceTranscript("benchmark transcript", "en", 0.9)


def render_markdown(comparisons: tuple[BenchmarkComparison, ...]) -> str:
    """Render compact benchmark evidence for the architecture document."""
    lines = [
        "| Utterance | Strategy | STT calls | Audio processed | Largest partial | "
        "Final input | Median Python overhead |",
        "| ---: | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for comparison in comparisons:
        for measurement in (comparison.legacy, comparison.rolling):
            lines.append(
                f"| {measurement.utterance_seconds:.0f} s | {measurement.strategy} | "
                f"{measurement.request_count} | "
                f"{measurement.processed_audio_seconds:.1f} audio-s | "
                f"{measurement.maximum_partial_audio_seconds:.1f} s | "
                f"{measurement.final_audio_seconds:.1f} s | "
                f"{measurement.median_orchestration_ms:.2f} ms |"
            )
        lines.append(
            f"| {comparison.legacy.utterance_seconds:.0f} s | rolling reduction | "
            f"- | {comparison.processed_audio_reduction_percent:.1f}% | - | - | - |"
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=15)
    arguments = parser.parse_args()
    comparisons = asyncio.run(benchmark(repeats=arguments.repeats))
    print(render_markdown(comparisons))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
