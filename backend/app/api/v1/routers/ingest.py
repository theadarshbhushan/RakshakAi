"""
Ingest router (/api/v1/ingest).
Ingests batches of real-time signals from edge device cameras and microphones.
Authenticates via machine API key (X-API-Key) or user bearer JWT with 'signals:write' permission.
TODO [STABILIZATION]: Router disabled and unmounted in main app during stabilization.
"""
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, status

from app.core.deps import get_ingest_principal
from app.fusion.corroboration import FusionEngine
from app.models.rules import RuleDocument
from app.models.signal import Signal
from app.schemas.domain import SignalCreateRequest

router = APIRouter(prefix="/ingest", tags=["Ingest"])


@router.post("/signals", status_code=status.HTTP_202_ACCEPTED)
async def ingest_signals(
    signals_batch: List[SignalCreateRequest],
    principal: Dict[str, Any] = Depends(get_ingest_principal),
):
    """
    Ingest a batch of video, audio, or access control signals from edge devices.
    Feeds signals directly into the organization's real-time Fusion Engine.
    """
    org_id = principal["org_id"]

    # Load active rules
    active_rules = await RuleDocument.find_one({"org_id": org_id, "is_active": True})
    rules_dict = active_rules.model_dump() if active_rules else {}
    fusion_engine = FusionEngine(org_id, rules_dict)

    processed_count = 0
    for req in signals_batch:
        signal = Signal(
            org_id=org_id,
            site_id=req.site_id or principal.get("site_id"),
            modality=req.modality,
            kind=req.kind,
            zone_id=req.zone_id,
            camera_id=req.camera_id,
            score=req.score,
            threshold=req.threshold,
            details=req.details,
            suppressed=req.suppressed,
            suppress_reason=req.suppress_reason,
            evidence_path=req.evidence_path,
            source=principal.get("type", "edge_device"),
        )
        await fusion_engine.ingest_signal(signal)
        processed_count += 1

    return {
        "message": f"Successfully ingested {processed_count} signal(s)",
        "count": processed_count,
        "org_id": org_id,
    }
