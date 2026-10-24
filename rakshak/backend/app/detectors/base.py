"""
Abstract Detector interface for RakshakAI.
Clean pluggable interface enabling modular swapping between mock detectors and real ML models.
"""
from abc import ABC, abstractmethod
import asyncio
from datetime import datetime, timezone, timedelta
import time
from typing import Callable, Awaitable, Optional

from app.models import Signal


class SimulationClock:
    """
    Simulation Clock that maps real-world execution seconds to simulated hostel timeline.
    Allows time compression (e.g. speed=50.0x) so lengthy scenarios run in seconds during tests.
    """
    def __init__(self, start_sim_time: datetime, speed: float = 1.0):
        if start_sim_time.tzinfo is None:
            start_sim_time = start_sim_time.replace(tzinfo=timezone.utc)
        self.start_sim_time = start_sim_time
        self.speed = max(0.001, float(speed))
        self.start_real_time = time.monotonic()
        self._stopped = False

    def now(self) -> datetime:
        """Returns the current simulated time."""
        elapsed_real = time.monotonic() - self.start_real_time
        elapsed_sim = elapsed_real * self.speed
        return self.start_sim_time + timedelta(seconds=elapsed_sim)

    async def sleep_until(self, target_sim_time: datetime) -> None:
        """Sleep until the simulation clock reaches target_sim_time."""
        if target_sim_time.tzinfo is None:
            target_sim_time = target_sim_time.replace(tzinfo=timezone.utc)
        current = self.now()
        diff_sim_seconds = (target_sim_time - current).total_seconds()
        if diff_sim_seconds > 0 and not self._stopped:
            real_seconds_to_sleep = diff_sim_seconds / self.speed
            await asyncio.sleep(real_seconds_to_sleep)

    async def sleep(self, sim_seconds: float) -> None:
        """Sleep for sim_seconds in simulated time."""
        if sim_seconds > 0 and not self._stopped:
            await asyncio.sleep(sim_seconds / self.speed)

    def stop(self) -> None:
        self._stopped = True

    @property
    def is_stopped(self) -> bool:
        return self._stopped


class BaseDetector(ABC):
    """
    Abstract interface for all video, audio, and sensor detectors.
    """
    def __init__(self) -> None:
        self.running: bool = False

    @abstractmethod
    async def start(
        self,
        source: str,
        zone_id: str,
        sim_clock: SimulationClock,
        emit_callback: Callable[[Signal], Awaitable[None]],
    ) -> None:
        """
        Start the detector listening or processing source frames/events.
        Emits Signal objects asynchronously through emit_callback.
        """
        pass

    @abstractmethod
    async def stop(self) -> None:
        """Stop detector execution cleanly."""
        pass
