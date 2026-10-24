"""
Camera Health and Blind-Spot Compensation Service.
Manages camera health status (ok | degraded | tampered | offline) and automatic
blind-spot compensation for affected zones:
- Marks zone as blind spot while camera is tampered or offline.
- Temporarily lowers distress_audio threshold by 0.1 (floor 0.2) with reason 'blind_spot_compensation'.
- Automatically reverts threshold and clears blind spot when camera is ok again.
- Broadcasts WebSocket event 'camera.health_changed'.
- NEVER modifies the permanent calibration history (ThresholdHistory).
"""
from datetime import datetime, timezone
import logging
from typing import Any, Dict, Optional

from app.core.errors import NotFoundError
from app.models.rules import RuleDocument
from app.models.zone import Camera, Zone
from app.realtime.ws import ws_hub

logger = logging.getLogger("rakshakai.camera_health")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class CameraHealthService:
    @staticmethod
    async def update_camera_health(
        org_id: str,
        camera_id: str,
        health_status: str,
        health_reason: Optional[str] = None,
        last_frame_at: Optional[datetime] = None,
    ) -> Camera:
        """
        Update camera health status, apply/revert blind-spot compensation,
        and broadcast camera.health_changed WebSocket event.
        """
        camera = await Camera.find_one({"org_id": org_id, "camera_id": camera_id})
        if not camera:
            raise NotFoundError("Camera", camera_id)

        old_status = camera.health_status
        camera.health_status = health_status
        camera.health_reason = health_reason
        if last_frame_at:
            camera.last_frame_at = last_frame_at
        elif health_status == "ok" and not camera.last_frame_at:
            camera.last_frame_at = utc_now()

        await camera.save()
        logger.info(f"Camera {camera_id} health updated to '{health_status}' (reason: {health_reason})")

        zone = await Zone.find_one({"org_id": org_id, "zone_id": camera.zone_id})

        # -------------------------------------------------------------
        # Blind-Spot Compensation Activation (tampered | offline)
        # -------------------------------------------------------------
        if health_status in ("tampered", "offline"):
            if zone:
                zone.is_blind_spot = True
                zone.blind_spot_reason = health_reason or (
                    "camera tampered" if health_status == "tampered" else "camera offline"
                )

                # Lower distress_audio threshold in RuleDocument by 0.1 (floor 0.2)
                active_rules = await RuleDocument.find_one({"org_id": org_id, "is_active": True})
                if active_rules:
                    if camera.zone_id not in active_rules.zones:
                        active_rules.zones[camera.zone_id] = {"thresholds": {"distress_audio": 0.35}}
                    z_conf = active_rules.zones[camera.zone_id]
                    thresholds = z_conf.setdefault("thresholds", {})

                    # Only lower if not already compensated
                    if "blind_spot_compensation" not in z_conf:
                        orig_val = float(thresholds.get("distress_audio", 0.35))
                        lowered_val = max(0.20, round(orig_val - 0.10, 2))
                        thresholds["distress_audio"] = lowered_val
                        z_conf["thresholds"] = thresholds

                        comp_info = {
                            "reason": "blind_spot_compensation",
                            "detector": "distress_audio",
                            "original_threshold": orig_val,
                            "adjusted_threshold": lowered_val,
                            "camera_id": camera_id,
                            "applied_at": utc_now().isoformat(),
                        }
                        z_conf["blind_spot_compensation"] = comp_info
                        zone.blind_spot_adjustments = comp_info
                        active_rules.zones[camera.zone_id] = z_conf
                        await active_rules.save()
                        logger.info(
                            f"Blind-spot compensation applied for zone '{zone.zone_id}': "
                            f"distress_audio threshold lowered from {orig_val} to {lowered_val} (floor 0.2)."
                        )

                await zone.save()

        # -------------------------------------------------------------
        # Blind-Spot Compensation Reversion (ok)
        # -------------------------------------------------------------
        elif health_status == "ok":
            if zone:
                # Check if any OTHER camera in the zone is still tampered or offline
                other_bad = await Camera.find_one({
                    "org_id": org_id,
                    "zone_id": camera.zone_id,
                    "camera_id": {"$ne": camera_id},
                    "health_status": {"$in": ["tampered", "offline"]},
                })
                if not other_bad:
                    zone.is_blind_spot = False
                    zone.blind_spot_reason = None

                    # Revert distress_audio threshold in RuleDocument
                    active_rules = await RuleDocument.find_one({"org_id": org_id, "is_active": True})
                    if active_rules and camera.zone_id in active_rules.zones:
                        z_conf = active_rules.zones[camera.zone_id]
                        comp_info = z_conf.get("blind_spot_compensation")
                        if comp_info:
                            orig_val = float(comp_info.get("original_threshold", 0.35))
                            z_conf.get("thresholds", {})["distress_audio"] = orig_val
                            del z_conf["blind_spot_compensation"]
                            active_rules.zones[camera.zone_id] = z_conf
                            await active_rules.save()
                            logger.info(
                                f"Blind-spot compensation reverted for zone '{zone.zone_id}': "
                                f"distress_audio threshold restored to {orig_val}."
                            )

                    zone.blind_spot_adjustments = None
                    await zone.save()

        # -------------------------------------------------------------
        # Broadcast WebSocket event camera.health_changed
        # -------------------------------------------------------------
        await ws_hub.broadcast_to_org(
            org_id=org_id,
            event_type="camera.health_changed",
            data={
                "camera_id": camera.camera_id,
                "zone_id": camera.zone_id,
                "health_status": camera.health_status,
                "health_reason": camera.health_reason,
                "last_frame_at": camera.last_frame_at.isoformat() if camera.last_frame_at else None,
                "is_blind_spot": zone.is_blind_spot if zone else False,
                "blind_spot_reason": zone.blind_spot_reason if zone else None,
            },
        )

        return camera
