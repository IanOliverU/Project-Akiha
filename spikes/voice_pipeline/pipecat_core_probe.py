"""Minimal executable Pipecat core-pipeline compatibility probe."""

from __future__ import annotations

import asyncio
import importlib.metadata
import json
import sys
from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class ProbeResult:
    python_version: str
    pipecat_version: str
    received_text: tuple[str, ...]
    end_frame_seen: bool


async def run_probe() -> ProbeResult:
    """Pass text and termination frames through a real Pipecat pipeline."""
    from pipecat.frames.frames import EndFrame, TextFrame
    from pipecat.pipeline.pipeline import Pipeline
    from pipecat.pipeline.worker import PipelineWorker
    from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
    from pipecat.workers.runner import WorkerRunner

    class Recorder(FrameProcessor):
        def __init__(self) -> None:
            super().__init__()
            self.received_text: list[str] = []
            self.end_frame_seen = False

        async def process_frame(self, frame: object, direction: FrameDirection) -> None:
            await super().process_frame(frame, direction)
            if isinstance(frame, TextFrame):
                self.received_text.append(frame.text)
            elif isinstance(frame, EndFrame):
                self.end_frame_seen = True
            await self.push_frame(frame, direction)

    recorder = Recorder()
    pipeline = Pipeline([recorder])
    worker = PipelineWorker(
        pipeline,
        enable_rtvi=False,
        enable_turn_tracking=False,
        idle_timeout_secs=None,
    )
    runner = WorkerRunner(handle_sigint=False)
    await runner.add_workers(worker)
    runner_task = asyncio.create_task(runner.run())
    await asyncio.sleep(0)
    await worker.queue_frames((TextFrame("local"), TextFrame("hosted"), EndFrame()))
    await asyncio.wait_for(runner_task, timeout=5.0)

    return ProbeResult(
        python_version=sys.version.split()[0],
        pipecat_version=importlib.metadata.version("pipecat-ai"),
        received_text=tuple(recorder.received_text),
        end_frame_seen=recorder.end_frame_seen,
    )


if __name__ == "__main__":
    print(json.dumps(asdict(asyncio.run(run_probe())), indent=2))
