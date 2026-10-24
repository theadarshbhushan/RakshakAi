"""
Concrete TenantScopedRepository classes for all aggregate collections.
All database access is strictly isolated by tenant org_id.
"""
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
import json
import hashlib
from beanie import PydanticObjectId

from app.db.tenant import TenantScopedRepository
from app.models.organization import Site
from app.models.zone import Zone, Camera
from app.models.signal import Signal, AccessEvent
from app.models.incident import Incident, Feedback, ThresholdHistory
from app.models.rules import RuleDocument
from app.models.user import ApiKey, Invitation
from app.models.privacy import BreakglassGrant
from app.models.audit import AuditLog, utc_now

GENESIS_PREV_HASH = "0" * 64


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
    def canonical_json(seq: int, ts_iso: str, actor: Dict[str, Any], action: str, target: str, reason: str, ip: Optional[str], user_agent: Optional[str], request_id: Optional[str]) -> str:
        data = {
            "action": action,
            "actor": actor,
            "ip": ip or "",
            "reason": reason,
            "request_id": request_id or "",
            "seq": seq,
            "target": target,
            "ts": ts_iso,
            "user_agent": user_agent or "",
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
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        ts_iso = timestamp.isoformat()

        # Find latest record for this tenant
        last_rec = await AuditLog.find({"org_id": self.org_id}).sort("-seq").first_or_none()
        if last_rec is None:
            seq = 1
            prev_hash = GENESIS_PREV_HASH
        else:
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
        records = await AuditLog.find({"org_id": self.org_id}).sort("+seq").to_list()
        if not records:
            return {"valid": True, "total_records": 0, "message": "Audit log is empty."}

        expected_prev = GENESIS_PREV_HASH

        for r in records:
            if r.prev_hash != expected_prev:
                return {
                    "valid": False,
                    "total_records": len(records),
                    "broken_at_seq": r.seq,
                    "message": f"Broken chain link at seq {r.seq}: previous hash mismatch",
                }

            ts_iso = r.ts.replace(tzinfo=timezone.utc).isoformat() if r.ts.tzinfo is None else r.ts.isoformat()
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
