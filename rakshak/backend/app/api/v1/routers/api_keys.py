"""
API Keys router (/api/v1/api-keys).
Provisioning and revoking machine API keys for edge device detectors.
TODO [STABILIZATION]: Router disabled and unmounted in main app during stabilization.
"""
from typing import List

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, status

from app.core.deps import get_current_user, require_permission
from app.core.errors import NotFoundError
from app.models.user import ApiKey, User, utc_now
from app.repositories.repos import AuditRepository
from app.schemas.organization import (
    ApiKeyCreateRequest,
    ApiKeyCreateResponse,
    ApiKeyResponse,
)
from app.services.org_service import OrgService

router = APIRouter(prefix="/api-keys", tags=["API Keys"])


@router.post("", response_model=ApiKeyCreateResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_permission("api_keys:manage"))])
async def create_api_key(
    payload: ApiKeyCreateRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Generate a new API key for edge device agents.
    Returns the full key ONCE: rk_live_<prefix>_<secret>.
    """
    key_doc, full_key = await OrgService.create_api_key(
        org_id=current_user.org_id,
        name=payload.name,
        scopes=payload.scopes,
        site_id=payload.site_id,
        actor=current_user,
    )

    return ApiKeyCreateResponse(
        id=str(key_doc.id),
        name=key_doc.name,
        prefix=key_doc.prefix,
        key=full_key,
        scopes=key_doc.scopes,
        site_id=key_doc.site_id,
        created_at=key_doc.created_at,
    )


@router.get("", response_model=List[ApiKeyResponse], dependencies=[Depends(require_permission("api_keys:manage"))])
async def list_api_keys(current_user: User = Depends(get_current_user)):
    """List all API keys for the current organization (prefix and metadata only)."""
    keys = await ApiKey.find(ApiKey.org_id == current_user.org_id).to_list()
    return [
        ApiKeyResponse(
            id=str(k.id),
            name=k.name,
            prefix=k.prefix,
            scopes=k.scopes,
            site_id=k.site_id,
            created_at=k.created_at,
            last_used_at=k.last_used_at,
            revoked_at=k.revoked_at,
        )
        for k in keys
    ]


@router.delete("/{key_id}", dependencies=[Depends(require_permission("api_keys:manage"))])
async def revoke_api_key(key_id: str, current_user: User = Depends(get_current_user)):
    """Revoke an edge device API key."""
    key_doc = await ApiKey.find_one({"_id": PydanticObjectId(key_id), "org_id": current_user.org_id})
    if not key_doc:
        raise NotFoundError("ApiKey", key_id)

    key_doc.revoked_at = utc_now()
    await key_doc.save()

    audit_repo = AuditRepository(current_user.org_id)
    await audit_repo.record_audit(
        actor={"type": "user", "id": str(current_user.id), "email": current_user.email},
        action="api_key.revoked",
        target=f"api_key:{key_doc.id}",
        reason=f"Revoked API key '{key_doc.name}'.",
    )

    return {"message": "API key revoked successfully."}
