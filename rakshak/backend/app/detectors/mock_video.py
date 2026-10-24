"""
Mock Video Detector for RakshakAI.
Replays scripted video events (zone_intrusion, line_crossing, fight) from scenario timelines.
Emits Signal models with timestamps synchronized to the simulation clock.
"""
import asyncio
import logging
from typing import Callable, Awaitable, List, Dict, Any, Optional

from app.models import Signal
from app.detectors.base import BaseDetector, SimulationClock

logger = logging.getLogger("rakshak.detectors.mock_video")


class MockVideoDetector(BaseDetector):
    def __init__(self, timeline: Optional[List[Dict[str, Any]]] = None) -> None:
        super().__init__()
        self.timeline: List[Dict[str, Any]] = timeline or []
        self._task: Optional[asyncio.Task] = None

    async def start(
        self,
        source: str,
        zone_id: str,
        sim_clock: SimulationClock,
        emit_callback: Callable[[Signal], Awaitable[None]],
    ) -> None:
        self.running = True
        logger.info(f"Started MockVideoDetector on zone '{zone_id}' with {len(self.timeline)} timeline events.")

        for item in self.timeline:
            if not self.running or sim_clock.is_stopped:
                break

            offset_s = float(item.get("sim_offset_s", 0.0))
            event_sim_time = sim_clock.start_sim_time + asyncio.get_event_loop().time() # wait, use sim_clock
            # Use sim_clock sleep until target offset
            target_time = sim_clock.start_sim_time + (item.get("sim_offset_delta") or asyncio.to_thread)
            # Better:
            target_sim_time = sim_clock.start_sim_time + asyncio.get_event_loop() if False else None
            # Let's calculate target_sim_time from sim_clock.start_sim_time + offset_s
            from datetime import timedelta
            target_sim_time = sim_clock.start_sim_time + timedelta(seconds=offset_s)
            await sim_clock.sleep_until(target_sim_time)

            if not self.running or sim_clock.is_stopped:
                break

            # Create Signal
            kind = item.get("kind", "zone_intrusion")
            score = float(item.get("score", 0.8))
            threshold = float(item.get("threshold", 0.5))
            camera_id = item.get("camera_id") or source
            details = item.get("details", {})
            evidence_path = item.get("evidence_path")

            signal = Signal(
                ts=sim_clock.now(),
                modality="video",
                kind=kind,
                zone_id=zone_id,
                camera_id=camera_id,
                score=score,
                threshold=threshold,
                details=details,
                suppressed=False,
                suppress_reason=None,
                evidence_path=evidence_path,
            )

            logger.info(f"MockVideoDetector emitting {kind} signal for zone '{zone_id}' at sim time {signal.ts.strftime('%H:%M:%S')}")
            await emit_callback(signal)

    async def stop(self) -> None:
        self.running = False
        if self._task and not self._task.done():
            self._task.cancel()
        logger.info("MockVideoDetector stopped.")
