"""
Retention policy and evidence management for RakshakAI.
Enforces automatic data minimization:
- Deletes evidence files on disk older than retention_days.
- Nulls out evidence_path pointers on Signal documents.
- Maintains inventory of stored evidence and documents across all collections.
- Never auto-deletes confirmed incidents or the audit log.
"""
import logging
from datetime import timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from app.core.config import settings
from app.models.audit import AuditLog
from app.models.incident import Feedback, Incident, ThresholdHistory
from app.models.organization import Organization, Site
from app.models.privacy import BreakglassGrant
from app.models.signal import AccessEvent, Signal
from app.models.user import User, utc_now
from app.models.zone import Camera, Zone
from app.repositories.repos import AuditRepository

logger = logging.getLogger("rakshakai.privacy.retention")


async def execute_retention_purge(user: str = "system", org_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Purge evidence files and references older than retention_days.
    Logs actions in the tamper-evident audit log.
    """
    # If org_id specified, purge for that org; else for all orgs
    orgs = await Organization.find_all().to_list() if not org_id else [await Organization.get(__import__("beanie").PydanticObjectId(org_id))]

    total_deleted_files = 0
    total_updated_signals = 0

    for org in orgs:
        if not org:
            continue
        oid = str(org.id)
        retention_days = int(org.settings.get("retention_days", 7))
        cutoff = utc_now() - timedelta(days=retention_days)

        signals_to_purge = await Signal.find(
            Signal.org_id == oid,
            Signal.ts < cutoff,
            Signal.evidence_path != None,
        ).to_list()

        deleted_files_count = 0
        updated_signals_count = 0

        for sig in signals_to_purge:
            if sig.evidence_path:
                evidence_file = Path(sig.evidence_path)
                if not evidence_file.is_absolute():
                    evidence_file = settings.DATA_DIR / sig.evidence_path

                if evidence_file.exists() and evidence_file.is_file():
                    try:
                        evidence_file.unlink()
                        deleted_files_count += 1
                    except Exception as exc:
                        logger.warning(f"Could not delete evidence file {evidence_file}: {exc}")

                sig.evidence_path = None
                await sig.save()
                updated_signals_count += 1

        # Purge raw encrypted clips in data/evidence/restricted/raw/
        raw_dir = settings.DATA_DIR / "evidence" / "restricted" / "raw"
        retention_days_confirmed = int(org.settings.get("retention_days_confirmed", 30))
        cutoff_confirmed = utc_now() - timedelta(days=retention_days_confirmed)

        if raw_dir.exists():
            for enc_file in raw_dir.glob("*.enc"):
                inc_id = enc_file.stem
                try:
                    inc_doc = await Incident.find_one({"_id": __import__("beanie").PydanticObjectId(inc_id), "org_id": oid})
                except Exception:
                    inc_doc = await Incident.find_one({"_id": inc_id, "org_id": oid})

                if inc_doc:
                    is_confirmed = (inc_doc.status == "confirmed")
                    clip_cutoff = cutoff_confirmed if is_confirmed else cutoff
                    inc_ts = inc_doc.created_ts
                    if inc_ts.tzinfo is None:
                        inc_ts = inc_ts.replace(tzinfo=timezone.utc)
                    if inc_ts < clip_cutoff:
                        try:
                            enc_file.unlink()
                            deleted_files_count += 1
                        except Exception as e:
                            logger.warning(f"Could not purge raw clip {enc_file}: {e}")

        total_deleted_files += deleted_files_count
        total_updated_signals += updated_signals_count

        audit_repo = AuditRepository(oid)
        await audit_repo.record_audit(
            actor={"type": "user" if user != "scheduler" else "system", "id": user, "email": user},
            action="retention.purge",
            target="evidence_storage",
            reason=f"Purged {deleted_files_count} files and updated {updated_signals_count} signals (retention {retention_days}d, confirmed {retention_days_confirmed}d).",
        )

    summary = {
        "deleted_files": total_deleted_files,
        "updated_signals": total_updated_signals,
    }

    logger.info(f"Retention purge completed: {summary}")
    return summary


async def get_privacy_inventory() -> Dict[str, Any]:
    """
    Return counts of stored evidence files and documents per collection.
    """
    doc_counts = {
        "organizations": await Organization.count(),
        "sites": await Site.count(),
        "users": await User.count(),
        "cameras": await Camera.count(),
        "zones": await Zone.count(),
        "signals": await Signal.count(),
        "incidents": await Incident.count(),
        "feedback": await Feedback.count(),
        "threshold_history": await ThresholdHistory.count(),
        "audit_log": await AuditLog.count(),
        "breakglass_grants": await BreakglassGrant.count(),
        "access_events": await AccessEvent.count(),
    }

    evidence_dir = settings.EVIDENCE_DIR
    public_files = 0
    restricted_files = 0
    total_bytes = 0

    if evidence_dir.exists():
        pub_dir = evidence_dir / "public"
        if pub_dir.exists():
            for f in pub_dir.glob("*"):
                if f.is_file():
                    public_files += 1
                    total_bytes += f.stat().st_size

        res_dir = evidence_dir / "restricted"
        if res_dir.exists():
            for f in res_dir.glob("*"):
                if f.is_file():
                    restricted_files += 1
                    total_bytes += f.stat().st_size

    return {
        "document_counts": doc_counts,
        "evidence_storage": {
            "public_files_count": public_files,
            "restricted_files_count": restricted_files,
            "total_files_count": public_files + restricted_files,
            "total_size_bytes": total_bytes,
            "total_size_kb": round(total_bytes / 1024, 2),
        },
        "timestamp": utc_now().isoformat(),
    }
