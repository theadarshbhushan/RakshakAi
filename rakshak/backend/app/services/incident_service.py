"""
Incident lifecycle management: Acknowledgment, Human Review, Feedback, and False Alarm Calibration.
"""
from typing import List, Optional

from beanie import PydanticObjectId

from app.core.errors import AppError, NotFoundError
from app.models.incident import Feedback, Incident, ThresholdHistory
from app.models.rules import RuleDocument
from app.models.signal import Signal
from app.models.user import User, utc_now
from app.realtime.ws import ws_hub
from app.repositories.repos import AuditRepository


class IncidentService:
    @staticmethod
    async def acknowledge_incident(org_id: str, incident_id: str, user: User) -> Incident:
        """Acknowledge incident by a human guard/warden/admin."""
        incident = await Incident.find_one({"_id": PydanticObjectId(incident_id), "org_id": org_id})
        if not incident:
            raise NotFoundError("Incident", incident_id)

        now = utc_now()
        incident.status = "acknowledged"
        incident.acknowledged_by = user.email
        incident.acknowledged_ts = now
        incident.updated_ts = now
        await incident.save()

        audit_repo = AuditRepository(org_id)
        await audit_repo.record_audit(
            actor={"type": "user", "id": str(user.id), "email": user.email},
            action="incident.acknowledged",
            target=f"incident:{incident.id}",
            reason=f"Incident acknowledged by {user.email}.",
        )

        await ws_hub.broadcast_to_org(
            org_id=org_id,
            event_type="incident.updated",
            data={
                "id": str(incident.id),
                "status": incident.status,
                "acknowledged_by": incident.acknowledged_by,
                "acknowledged_ts": incident.acknowledged_ts.isoformat(),
            },
        )

        return incident

    @staticmethod
    async def review_incident(
        org_id: str,
        incident_id: str,
        label: str,
        note: Optional[str],
        user: User,
    ) -> Incident:
        """
        Human review of incident: confirmed | false_alarm | investigating.
        Only a human review can set confirmed or false_alarm.
        Triggers auto-calibration threshold raising on false_alarm.
        """
        if label not in ("confirmed", "false_alarm", "investigating"):
            raise AppError("Label must be one of: confirmed, false_alarm, investigating", status_code=400)

        if label in ("confirmed", "false_alarm") and not note:
            raise AppError(f"A review note is required when marking an incident as {label}.", status_code=400)

        incident = await Incident.find_one({"_id": PydanticObjectId(incident_id), "org_id": org_id})
        if not incident:
            raise NotFoundError("Incident", incident_id)

        now = utc_now()
        incident.status = label
        incident.reviewer = user.email
        incident.review_note = note
        incident.reviewed_ts = now
        incident.updated_ts = now
        await incident.save()

        # Save Feedback
        feedback = Feedback(
            org_id=org_id,
            incident_id=str(incident.id),
            user=user.email,
            label=label,
            note=note,
            ts=now,
        )
        await feedback.insert()

        audit_repo = AuditRepository(org_id)
        await audit_repo.record_audit(
            actor={"type": "user", "id": str(user.id), "email": user.email},
            action="incident.reviewed",
            target=f"incident:{incident.id}",
            reason=f"Reviewed incident as '{label}': {note or ''}",
        )

        # On FALSE_ALARM: Auto-calibration threshold adjustment
        if label == "false_alarm":
            await IncidentService._calibrate_false_alarm(org_id, incident, user)

        await ws_hub.broadcast_to_org(
            org_id=org_id,
            event_type="incident.updated",
            data={
                "id": str(incident.id),
                "status": incident.status,
                "reviewer": incident.reviewer,
                "review_note": incident.review_note,
                "reviewed_ts": incident.reviewed_ts.isoformat(),
            },
        )

        return incident

    @staticmethod
    async def _calibrate_false_alarm(org_id: str, incident: Incident, user: User) -> None:
        """
        Raise detection threshold by +0.05 (capped at 0.90) for all detectors that contributed to false alarm.
        """
        active_rules = await RuleDocument.find_one({"org_id": org_id, "is_active": True})
        if not active_rules:
            return

        # Fetch signals attached to incident
        signals: List[Signal] = []
        for sid in incident.signal_ids:
            s_doc = await Signal.get(PydanticObjectId(sid))
            if s_doc and not s_doc.suppressed:
                signals.append(s_doc)

        zone_rules = active_rules.zones.get(incident.zone_id, {})
        current_thresholds = zone_rules.get("thresholds", {
            "zone_intrusion": 0.50,
            "distress_audio": 0.35,
            "fight": 0.60,
        })

        now = utc_now()
        calibrated_kinds = set(s.kind for s in signals)

        for kind in calibrated_kinds:
            if kind in current_thresholds:
                old_val = float(current_thresholds[kind])
                new_val = min(0.90, round(old_val + 0.05, 2))
                current_thresholds[kind] = new_val

                history = ThresholdHistory(
                    org_id=org_id,
                    zone_id=incident.zone_id,
                    detector=kind,
                    old_value=old_val,
                    new_value=new_val,
                    reason=f"False alarm review on incident {incident.id}",
                    ts=now,
                    reverted=False,
                    changed_by=user.email,
                )
                await history.insert()

        active_rules.zones[incident.zone_id]["thresholds"] = current_thresholds
        active_rules.updated_at = now
        active_rules.updated_by = user.email
        await active_rules.save()

    @staticmethod
    async def revert_calibration(org_id: str, history_id: str, user: User) -> ThresholdHistory:
        """Revert a calibration threshold modification back to old_value."""
        history = await ThresholdHistory.find_one({"_id": PydanticObjectId(history_id), "org_id": org_id})
        if not history:
            raise NotFoundError("ThresholdHistory", history_id)

        if history.reverted:
            raise AppError("Threshold change has already been reverted.", status_code=400)

        active_rules = await RuleDocument.find_one({"org_id": org_id, "is_active": True})
        if active_rules and history.zone_id in active_rules.zones:
            active_rules.zones[history.zone_id]["thresholds"][history.detector] = history.old_value
            active_rules.updated_at = utc_now()
            active_rules.updated_by = user.email
            await active_rules.save()

        history.reverted = True
        await history.save()

        audit_repo = AuditRepository(org_id)
        await audit_repo.record_audit(
            actor={"type": "user", "id": str(user.id), "email": user.email},
            action="calibration.reverted",
            target=f"threshold_history:{history.id}",
            reason=f"Reverted threshold for {history.zone_id}/{history.detector} from {history.new_value} back to {history.old_value}.",
        )

        return history
