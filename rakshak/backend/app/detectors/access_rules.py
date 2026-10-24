"""
Real Access Rules Engine for RakshakAI (no ML required).
Evaluates access events against:
1. Curfew hours rule (e.g. 23:00 - 05:30 for residents)
2. Restricted zone role permissions (e.g. Terrace restricted to warden/maintenance)
3. Tailgating correlation: compares line crossings vs granted card swipes at entry doors
"""
from datetime import datetime, time, timedelta, timezone
import logging
from typing import Callable, Awaitable, Dict, Any, Optional

from app.models.signal import Signal, AccessEvent
from app.models.zone import Zone

logger = logging.getLogger("rakshakai.detectors.access_rules")


class AccessRulesEngine:
    def __init__(self, org_id: str, rules_config: Dict[str, Any]) -> None:
        self.org_id = org_id
        self.rules = rules_config

    def _is_in_curfew(self, event_time: datetime, curfew_conf: Dict[str, Any]) -> bool:
        start_str = curfew_conf.get("start", "23:00")
        end_str = curfew_conf.get("end", "05:30")
        sh, sm = map(int, start_str.split(":"))
        eh, em = map(int, end_str.split(":"))

        t = event_time.time()
        start_time = time(sh, sm)
        end_time = time(eh, em)

        # Overnight curfew: e.g. 23:00 to 05:30
        if start_time > end_time:
            return t >= start_time or t <= end_time
        return start_time <= t <= end_time

    async def evaluate_access_event(
        self,
        event: AccessEvent,
        emit_callback: Callable[[Signal], Awaitable[None]],
    ) -> None:
        """
        Evaluate a single access event for curfew and restricted access violations.
        """
        # 1. Curfew check
        curfew_conf = self.rules.get("curfew", {})
        applies_roles = curfew_conf.get("applies_to_roles", ["resident"])
        if event.role in applies_roles and self._is_in_curfew(event.ts, curfew_conf):
            logger.info(f"Curfew violation triggered for {event.role} #{event.pseudo_id} at door {event.door_id}")
            signal = Signal(
                org_id=self.org_id,
                site_id=event.site_id,
                ts=event.ts,
                modality="access",
                kind="curfew_violation",
                zone_id=event.zone_id,
                score=1.0,
                threshold=0.5,
                details={
                    "rule": "curfew",
                    "role": event.role,
                    "door_id": event.door_id,
                    "time": event.ts.strftime("%H:%M:%S"),
                    "pseudo_id": event.pseudo_id,
                },
                suppressed=False,
                source="access_engine",
            )
            await emit_callback(signal)

        # 2. Restricted zone check
        zones_conf = self.rules.get("zones", {})
        zone_info = zones_conf.get(event.zone_id)
        if zone_info and zone_info.get("type") == "restricted":
            allowed = zone_info.get("allowed_roles", [])
            if event.role not in allowed:
                logger.info(f"Restricted access violation triggered for {event.role} in {event.zone_id}")
                signal = Signal(
                    org_id=self.org_id,
                    site_id=event.site_id,
                    ts=event.ts,
                    modality="access",
                    kind="restricted_access",
                    zone_id=event.zone_id,
                    score=1.0,
                    threshold=0.5,
                    details={
                        "rule": "restricted_zone",
                        "zone_id": event.zone_id,
                        "role": event.role,
                        "pseudo_id": event.pseudo_id,
                        "door_id": event.door_id,
                        "result": event.result,
                    },
                    suppressed=False,
                    source="access_engine",
                )
                await emit_callback(signal)

    async def evaluate_tailgating(
        self,
        door_id: str,
        zone_id: str,
        window_center_ts: datetime,
        crossings_count: int,
        emit_callback: Callable[[Signal], Awaitable[None]],
        site_id: Optional[str] = None,
    ) -> Optional[Signal]:
        """
        Correlate video line crossings at turnstile vs granted card swipes.
        """
        window_sec = float(self.rules.get("tailgating", {}).get("window_seconds", 5))
        start_ts = window_center_ts - timedelta(seconds=window_sec)
        end_ts = window_center_ts + timedelta(seconds=window_sec)

        # Count granted 'in' swipes at this door during the window
        swipes_count = await AccessEvent.find({
            "org_id": self.org_id,
            "door_id": door_id,
            "direction": "in",
            "result": "granted",
            "ts": {"$gte": start_ts, "$lte": end_ts},
        }).count()

        if crossings_count > swipes_count:
            logger.info(
                f"Tailgating detected at door '{door_id}': {crossings_count} crossings vs {swipes_count} swipes"
            )
            signal = Signal(
                org_id=self.org_id,
                site_id=site_id,
                ts=window_center_ts,
                modality="access",
                kind="tailgating",
                zone_id=zone_id,
                score=1.0,
                threshold=0.5,
                details={
                    "people_count": crossings_count,
                    "swipe_count": swipes_count,
                    "door_id": door_id,
                },
                suppressed=False,
                source="access_engine",
            )
            await emit_callback(signal)
            return signal
        return None
