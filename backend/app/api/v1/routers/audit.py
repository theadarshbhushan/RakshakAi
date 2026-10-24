"""
Audit router (/api/v1/audit).
Append-only, tamper-evident cryptographic hash chain verification.
No update or delete endpoints exist.
"""
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Query

from app.core.deps import get_current_user, require_permission
from app.models.audit import AuditLog
from app.models.user import User
from app.repositories.repos import AuditRepository
from app.schemas.domain import AuditLogResponse, AuditVerifyResponse, PaginatedResponse

router = APIRouter(prefix="/audit", tags=["Audit Log"])


@router.get("", response_model=PaginatedResponse[AuditLogResponse], dependencies=[Depends(require_permission("audit:read"))])
async def list_audit_logs(
    current_user: User = Depends(get_current_user),
    action: Optional[str] = Query(None),
    actor_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    cursor: Optional[int] = Query(None, description="Sequence cursor (seq)"),
):
    """
    List immutable audit log records for current organization.
    Paginated by seq number in descending order.
    """
    query: Dict[str, Any] = {"org_id": current_user.org_id}
    if action:
        query["action"] = action
    if actor_id:
        query["actor.id"] = actor_id
    if cursor:
        query["seq"] = {"$lt": cursor}

    records = await AuditLog.find(query).sort("-seq").limit(limit + 1).to_list()
    has_next = len(records) > limit
    items_to_return = records[:limit]
    next_cursor = str(items_to_return[-1].seq) if has_next and items_to_return else None

    resp_items = [
        AuditLogResponse(
            seq=r.seq,
            ts=r.ts,
            actor=r.actor,
            action=r.action,
            target=r.target,
            reason=r.reason,
            ip=r.ip,
            user_agent=r.user_agent,
            request_id=r.request_id,
            prev_hash=r.prev_hash,
            hash=r.hash,
        )
        for r in items_to_return
    ]

    return PaginatedResponse(items=resp_items, next_cursor=next_cursor)


@router.get("/verify", response_model=AuditVerifyResponse, dependencies=[Depends(require_permission("audit:read"))])
async def verify_audit_chain(current_user: User = Depends(get_current_user)):
    """
    Recompute cryptographic SHA-256 hash chain from genesis to latest record.
    Identifies and reports the exact sequence number of any tampered or broken link.
    """
    audit_repo = AuditRepository(current_user.org_id)
    report = await audit_repo.verify_chain()
    return AuditVerifyResponse(
        valid=report.get("valid", True),
        total_records=report.get("total_records", 0),
        broken_at_seq=report.get("broken_at_seq"),
        message=report.get("message", ""),
    )
