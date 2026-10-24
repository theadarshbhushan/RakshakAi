"""
Concrete TenantScopedRepository classes for all aggregate collections.
All database access is strictly isolated by tenant org_id.
"""
import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.db.tenant import TenantScopedRepository
from app.models.audit import AuditLog, utc_now
from app.models.incident import Feedback, Incident, ThresholdHistory
from app.models.organization import Site
from app.models.privacy import BreakglassGrant
from app.models.signal import AccessEvent, Signal
from app.models.user import ApiKey, Invitation
from app.models.zone import Camera, Zone

GENESIS_PREV_HASH = "0" * 64


def format_iso_canonical(dt: datetime) -> str:
    """Format datetime into deterministic canonical string for hash chain verification."""
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


class SiteRepository(TenantScopedRepository[Site]):
    def __init__(self, org_id: str) -> None:
        super().__init__(Site, org_id)


class ZoneRepository(TenantScopedRepository[Zone]):
    def __init__(self, org_id: str) -> None:
        super().__init__(Zone, org_id)

    async def get_by_zone_id(self, zone_id: str) -> Optional[Zone]:
        return await self.find_one({"zone_id": zone_id})


class CameraRepository(TenantScopedRepository[Camera]):
    def __init__(self, org_id: str) -> None:
        super().__init__(Camera, org_id)

    async def get_by_camera_id(self, camera_id: str) -> Optional[Camera]:
        return await self.find_one({"camera_id": camera_id})


class SignalRepository(TenantScopedRepository[Signal]):
    def __init__(self, org_id: str) -> None:
        super().__init__(Signal, org_id)


class AccessEventRepository(TenantScopedRepository[AccessEvent]):
    def __init__(self, org_id: str) -> None:
        super().__init__(AccessEvent, org_id)


class IncidentRepository(TenantScopedRepository[Incident]):
    def __init__(self, org_id: str) -> None:
        super().__init__(Incident, org_id)

    async def find_open_incident_for_fusion(
        self,
        zone_ids: List[str],
        since_ts: datetime,
    ) -> Optional[Incident]:
        """Find an open incident in matching zones within fusion window."""
        query = {
            "org_id": self.org_id,
            "status": {"$in": ["new", "acknowledged", "investigating"]},
            "zone_id": {"$in": zone_ids},
            "updated_ts": {"$gte": since_ts},
        }
        return await Incident.find_one(query)


class FeedbackRepository(TenantScopedRepository[Feedback]):
    def __init__(self, org_id: str) -> None:
        super().__init__(Feedback, org_id)


class ThresholdHistoryRepository(TenantScopedRepository[ThresholdHistory]):
    def __init__(self, org_id: str) -> None:
        super().__init__(ThresholdHistory, org_id)


class ApiKeyRepository(TenantScopedRepository[ApiKey]):
    def __init__(self, org_id: str) -> None:
        super().__init__(ApiKey, org_id)


class InvitationRepository(TenantScopedRepository[Invitation]):
    def __init__(self, org_id: str) -> None:
        super().__init__(Invitation, org_id)


class BreakglassRepository(TenantScopedRepository[BreakglassGrant]):
    def __init__(self, org_id: str) -> None:
        super().__init__(BreakglassGrant, org_id)


class AuditRepository(TenantScopedRepository[AuditLog]):
    def __init__(self, org_id: str) -> None:
        super().__init__(AuditLog, org_id)

    @staticmethod
    def canonical_json(
        seq: int,
        ts_iso: str,
        actor: Dict[str, Any],
        action: str,
        target: str,
        reason: str,
        ip: Optional[str],
        user_agent: Optional[str],
        request_id: Optional[str],
    ) -> str:
        data = {
            "action": str(action),
            "actor": {str(k): str(v) for k, v in sorted(actor.items())},
            "ip": str(ip or ""),
            "reason": str(reason),
            "request_id": str(request_id or ""),
            "seq": int(seq),
            "target": str(target),
            "ts": str(ts_iso),
            "user_agent": str(user_agent or ""),
        }
        return json.dumps(data, sort_keys=True, separators=(",", ":"))

    @staticmethod
    def compute_hash(prev_hash: str, canonical_payload: str) -> str:
        combined = f"{prev_hash}{canonical_payload}".encode("utf-8")
        return hashlib.sha256(combined).hexdigest()

    async def record_audit(
        self,
        actor: Dict[str, Any],
        action: str,
        target: str,
        reason: str,
        ip: Optional[str] = None,
        user_agent: Optional[str] = None,
        request_id: Optional[str] = None,
        ts: Optional[datetime] = None,
    ) -> AuditLog:
        """Append-only tamper-evident audit record with cryptographic hash chain."""
        timestamp = ts or utc_now()
        # Truncate to millisecond precision to match MongoDB BSON date serialization
        timestamp = timestamp.replace(microsecond=(timestamp.microsecond // 1000) * 1000)
        ts_iso = format_iso_canonical(timestamp)

        # Find latest record for this tenant
        all_recs = await AuditLog.find({"org_id": self.org_id}).to_list()
        if not all_recs:
            seq = 1
            prev_hash = GENESIS_PREV_HASH
        else:
            last_rec = max(all_recs, key=lambda r: r.seq)
            seq = last_rec.seq + 1
            prev_hash = last_rec.hash

        payload = self.canonical_json(seq, ts_iso, actor, action, target, reason, ip, user_agent, request_id)
        computed_hash = self.compute_hash(prev_hash, payload)

        entry = AuditLog(
            org_id=self.org_id,
            seq=seq,
            ts=timestamp,
            actor=actor,
            action=action,
            target=target,
            reason=reason,
            ip=ip,
            user_agent=user_agent,
            request_id=request_id,
            prev_hash=prev_hash,
            hash=computed_hash,
        )
        await entry.insert()
        return entry

    async def verify_chain(self) -> Dict[str, Any]:
        """Verify the integrity of this tenant's cryptographic audit hash chain."""
        all_recs = await AuditLog.find({"org_id": self.org_id}).to_list()
        if not all_recs:
            return {"valid": True, "total_records": 0, "message": "Audit log is empty."}

        records = sorted(all_recs, key=lambda r: r.seq)
        expected_prev = GENESIS_PREV_HASH

        for r in records:
            if r.prev_hash != expected_prev:
                return {
                    "valid": False,
                    "total_records": len(records),
                    "broken_at_seq": r.seq,
                    "message": f"Broken chain link at seq {r.seq}: previous hash mismatch",
                }

            ts_iso = format_iso_canonical(r.ts)
            payload = self.canonical_json(r.seq, ts_iso, r.actor, r.action, r.target, r.reason, r.ip, r.user_agent, r.request_id)
            computed = self.compute_hash(r.prev_hash, payload)

            if r.hash != computed:
                return {
                    "valid": False,
                    "total_records": len(records),
                    "broken_at_seq": r.seq,
                    "message": f"Tampering detected at seq {r.seq}: hash payload mismatch",
                }

            expected_prev = r.hash

        return {
            "valid": True,
            "total_records": len(records),
            "message": "Cryptographic audit chain is unbroken and valid.",
        }
