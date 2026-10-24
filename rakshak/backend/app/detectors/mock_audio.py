"""
Mock Audio Detector for RakshakAI.
Replays scripted acoustic events (distress_audio, shouting, screaming, celebration).
Supports multi-stage audio inference where stage 2 context filter suppresses ambient
non-emergency noises (e.g. party cheering or laughter), flagging suppress_reason.
"""
import asyncio
import logging
from datetime import timedelta
from typing import Any, Awaitable, Callable, Dict, List, Optional

from app.detectors.base import BaseDetector, SimulationClock
from app.models.signal import Signal

logger = logging.getLogger("rakshakai.detectors.mock_audio")


class MockAudioDetector(BaseDetector):
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
        logger.info(f"Started MockAudioDetector on zone '{zone_id}' with {len(self.timeline)} timeline events.")

        for item in self.timeline:
            if not self.running or sim_clock.is_stopped:
                break

            offset_s = float(item.get("sim_offset_s", 0.0))
            target_sim_time = sim_clock.start_sim_time + timedelta(seconds=offset_s)
            await sim_clock.sleep_until(target_sim_time)

            if not self.running or sim_clock.is_stopped:
                break

            kind = item.get("kind", "distress_audio")
            score = float(item.get("score", 0.75))
            threshold = float(item.get("threshold", 0.35))
            details = item.get("details", {})
            evidence_path = item.get("evidence_path")
            suppressed = bool(item.get("suppressed", False))
            suppress_reason = item.get("suppress_reason")

            context_label = details.get("context_label")
            if context_label in ("birthday_party", "celebration", "sports_cheer"):
                suppressed = True
                suppress_reason = (
                    f"Context filter: High ambient celebratory activity ({context_label}) "
                    f"filtered out non-emergency sound (context_ratio {details.get('context_ratio', 0.85):.2f})."
                )

            current_sim_time = sim_clock.now()

            evidence_expires_at = None
            if suppressed:
                evidence_expires_at = current_sim_time + timedelta(days=7)

            signal = Signal(
                org_id="",  # Injected by runner
                ts=current_sim_time,
                modality="audio",
                kind=kind,
                zone_id=zone_id,
                camera_id=None,
                score=score,
                threshold=threshold,
                details=details,
                suppressed=suppressed,
                suppress_reason=suppress_reason,
                evidence_path=evidence_path,
                evidence_expires_at=evidence_expires_at,
                source="mock_audio",
            )

            logger.info(
                f"MockAudioDetector emitting {kind} (suppressed={suppressed}) "
                f"for zone '{zone_id}' at sim time {signal.ts.strftime('%H:%M:%S')}"
            )
            await emit_callback(signal)

    async def stop(self) -> None:
        self.running = False
        if self._task and not self._task.done():
            self._task.cancel()
        logger.info("MockAudioDetector stopped.")
