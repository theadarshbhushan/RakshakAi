"""
Scenario Runner for RakshakAI demo and automated integration evaluation.
Replays scripted multi-modal timeline slices against the real Fusion and Access engines
using an accelerated SimulationClock.
"""
import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from app.core.config import settings
from app.detectors.access_rules import AccessRulesEngine
from app.detectors.base import SimulationClock
from app.detectors.mock_audio import MockAudioDetector
from app.detectors.mock_video import MockVideoDetector
from app.fusion.corroboration import FusionEngine
from app.models.incident import Feedback, Incident, ThresholdHistory
from app.models.rules import RuleDocument
from app.models.signal import AccessEvent, Signal
from app.repositories.repos import AuditRepository

logger = logging.getLogger("rakshakai.scenario_runner")

_active_simulations: Dict[str, asyncio.Task] = {}
_active_clocks: Dict[str, SimulationClock] = {}


class ScenarioRunner:
    @staticmethod
    def load_scenario(scenario_id: str) -> Dict[str, Any]:
        """Load scenario JSON by ID from data/scenarios directory."""
        scenario_file = settings.SCENARIOS_DIR / f"{scenario_id}.json"
        if not scenario_file.exists():
            # Try finding by plain id matching file stem
            for f in settings.SCENARIOS_DIR.glob("*.json"):
                if f.stem == scenario_id:
                    scenario_file = f
                    break
        if not scenario_file.exists():
            raise FileNotFoundError(f"Scenario '{scenario_id}' not found in {settings.SCENARIOS_DIR}")

        with open(scenario_file, "r", encoding="utf-8") as sf:
            return json.load(sf)

    @staticmethod
    def list_scenarios() -> List[Dict[str, Any]]:
        """List all available scenario definitions."""
        scenarios = []
        if settings.SCENARIOS_DIR.exists():
            for f in sorted(settings.SCENARIOS_DIR.glob("*.json")):
                try:
                    with open(f, "r", encoding="utf-8") as sf:
                        data = json.load(sf)
                        scenarios.append({
                            "id": data.get("id", f.stem),
                            "name": data.get("name", f.stem),
                            "sim_start": data.get("sim_start"),
                            "duration_s": data.get("duration_s"),
                        })
                except Exception as exc:
                    logger.warning(f"Error loading scenario {f}: {exc}")
        return scenarios

    @staticmethod
    async def run_scenario(org_id: str, scenario_data: Dict[str, Any], speed: float = 1.0) -> Dict[str, Any]:
        """
        Execute scenario simulation concurrently:
        - Access engine evaluates access log events
        - Mock video detectors emit video signals
        - Mock audio detectors emit audio signals
        - Fusion engine fuses non-suppressed signals and builds incidents in real-time
        """
        # Parse simulation start time
        sim_start_str = scenario_data.get("sim_start", "23:38:00")
        sh, sm, ss = map(int, sim_start_str.split(":"))
        base_today = datetime.now(timezone.utc).replace(hour=sh, minute=sm, second=ss, microsecond=0)

        sim_clock = SimulationClock(start_sim_time=base_today, speed=speed)
        _active_clocks[org_id] = sim_clock

        # Fetch active rules for org
        active_rules = await RuleDocument.find_one({"org_id": org_id, "is_active": True})
        rules_dict = active_rules.model_dump() if active_rules else {}

        fusion_engine = FusionEngine(org_id, rules_dict)
        access_engine = AccessRulesEngine(org_id, rules_dict)

        # Signal callback for all detectors
        door_crossings_count: Dict[str, int] = {}

        async def emit_signal(signal: Signal) -> None:
            signal.org_id = org_id
            if signal.kind == "line_crossing":
                door_id = signal.details.get("door_id", "door_block_b")
                door_crossings_count[door_id] = door_crossings_count.get(door_id, 0) + 1
                # Save line crossing signal
                await signal.insert()
                # Check tailgating
                await access_engine.evaluate_tailgating(
                    door_id=door_id,
                    zone_id=signal.zone_id,
                    window_center_ts=signal.ts,
                    crossings_count=door_crossings_count[door_id],
                    emit_callback=fusion_engine.ingest_signal,
                    site_id=signal.site_id,
                )
            else:
                await fusion_engine.ingest_signal(signal)

        # 1. Access log replay task
        async def replay_access_logs():
            for item in scenario_data.get("access_log_slice", []):
                if sim_clock.is_stopped:
                    break
                offset_s = float(item.get("sim_offset_s", 0.0))
                target_sim_time = sim_clock.start_sim_time + timedelta(seconds=offset_s)
                await sim_clock.sleep_until(target_sim_time)
                if sim_clock.is_stopped:
                    break

                access_event = AccessEvent(
                    org_id=org_id,
                    site_id=item.get("site_id"),
                    ts=sim_clock.now(),
                    pseudo_id=item.get("pseudo_id", "anon"),
                    role=item.get("role", "resident"),
                    door_id=item.get("door_id", "door_block_b"),
                    zone_id=item.get("zone_id", "block_b_entry"),
                    direction=item.get("direction", "in"),
                    result=item.get("result", "granted"),
                )
                await access_event.insert()
                await access_engine.evaluate_access_event(access_event, emit_signal)

        # 2. Video detectors tasks
        video_tasks = []
        for cam_data in scenario_data.get("cameras", []):
            detector = MockVideoDetector(timeline=cam_data.get("timeline", []))
            video_tasks.append(
                detector.start(
                    source=cam_data.get("camera_id", "cam"),
                    zone_id=cam_data.get("zone_id", "common"),
                    sim_clock=sim_clock,
                    emit_callback=emit_signal,
                )
            )

        # 3. Audio detectors tasks
        audio_tasks = []
        for audio_data in scenario_data.get("audio", []):
            detector = MockAudioDetector(timeline=audio_data.get("timeline", []))
            audio_tasks.append(
                detector.start(
                    source="mic",
                    zone_id=audio_data.get("zone_id", "common"),
                    sim_clock=sim_clock,
                    emit_callback=emit_signal,
                )
            )

        # Run all generators concurrently
        tasks = [replay_access_logs()] + video_tasks + audio_tasks
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, Exception):
                logger.error(f"Task error in scenario simulation: {r}", exc_info=r)
                raise r

        return {
            "scenario_id": scenario_data.get("id"),
            "status": "completed",
            "speed": speed,
            "sim_start": sim_start_str,
        }

    @staticmethod
    def stop_scenario(org_id: str) -> None:
        """Stop any running simulation for this organization."""
        clock = _active_clocks.get(org_id)
        if clock:
            clock.stop()
            del _active_clocks[org_id]

    @staticmethod
    async def reset_scenario(org_id: str, actor_email: str = "system") -> Dict[str, Any]:
        """
        Clears this organization's signals, incidents, feedback, access events, and threshold history.
        PRESERVES the audit log for compliance.
        """
        ScenarioRunner.stop_scenario(org_id)

        deleted_signals = await Signal.find(Signal.org_id == org_id).delete()
        deleted_incidents = await Incident.find(Incident.org_id == org_id).delete()
        deleted_feedback = await Feedback.find(Feedback.org_id == org_id).delete()
        deleted_access = await AccessEvent.find(AccessEvent.org_id == org_id).delete()
        deleted_history = await ThresholdHistory.find(ThresholdHistory.org_id == org_id).delete()

        audit_repo = AuditRepository(org_id)
        await audit_repo.record_audit(
            actor={"type": "user", "id": "reset_action", "email": actor_email},
            action="scenario.reset",
            target=f"organization:{org_id}",
            reason="Reset all signals, incidents, and access events for tenant demo environment.",
        )

        return {
            "message": "Scenario environment reset successfully.",
            "deleted_signals": deleted_signals.deleted_count if deleted_signals else 0,
            "deleted_incidents": deleted_incidents.deleted_count if deleted_incidents else 0,
            "deleted_access_events": deleted_access.deleted_count if deleted_access else 0,
            "deleted_feedback": deleted_feedback.deleted_count if deleted_feedback else 0,
            "deleted_threshold_history": deleted_history.deleted_count if deleted_history else 0,
        }
