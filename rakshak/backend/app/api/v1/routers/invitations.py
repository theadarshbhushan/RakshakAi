"""
Invitations router (/api/v1/invitations).
Issue team invitations and public invitation acceptance.
TODO [STABILIZATION]: Router disabled and unmounted in main app during stabilization.
"""
from typing import List

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, status

from app.core.config import settings
from app.core.deps import get_current_user, require_permission
from app.core.errors import NotFoundError
from app.core.logging import logger
from app.models.user import Invitation, User
from app.schemas.auth import UserSummaryResponse
from app.schemas.organization import (
    InvitationAcceptRequest,
    InvitationCreateRequest,
    InvitationResponse,
)
from app.services.org_service import OrgService

router = APIRouter(prefix="/invitations", tags=["Invitations"])


@router.post("", response_model=InvitationResponse, dependencies=[Depends(require_permission("invitations:manage"))])
async def create_invitation(
    payload: InvitationCreateRequest,
    current_user: User = Depends(get_current_user),
):
    """Invite a new user to join the organization (owner/admin only)."""
    invitation, raw_token = await OrgService.create_invitation(
        org_id=current_user.org_id,
        email=payload.email,
        role=payload.role,
        actor=current_user,
    )

    accept_link = f"{settings.FRONTEND_URL}/accept-invitation?token={raw_token}"
    logger.info(f"[DEV NOTIFICATION] Team invitation link for {payload.email}: {accept_link}")

    return InvitationResponse(
        id=str(invitation.id),
        org_id=invitation.org_id,
        email=invitation.email,
        role=invitation.role,
        created_at=invitation.created_at,
        expires_at=invitation.expires_at,
        accepted_at=invitation.accepted_at,
    )


@router.get("", response_model=List[InvitationResponse], dependencies=[Depends(require_permission("invitations:manage"))])
async def list_invitations(current_user: User = Depends(get_current_user)):
    """List pending invitations for the current organization."""
    invitations = await Invitation.find(
        Invitation.org_id == current_user.org_id,
        Invitation.accepted_at == None,
    ).to_list()

    return [
        InvitationResponse(
            id=str(inv.id),
            org_id=inv.org_id,
            email=inv.email,
            role=inv.role,
            created_at=inv.created_at,
            expires_at=inv.expires_at,
            accepted_at=inv.accepted_at,
        )
        for inv in invitations
    ]


@router.delete("/{invitation_id}", dependencies=[Depends(require_permission("invitations:manage"))])
async def revoke_invitation(invitation_id: str, current_user: User = Depends(get_current_user)):
    """Revoke a pending team invitation."""
    invitation = await Invitation.find_one({"_id": PydanticObjectId(invitation_id), "org_id": current_user.org_id})
    if not invitation:
        raise NotFoundError("Invitation", invitation_id)

    await invitation.delete()
    return {"message": "Invitation revoked successfully."}


@router.post("/accept", response_model=UserSummaryResponse, status_code=status.HTTP_201_CREATED)
async def accept_invitation(payload: InvitationAcceptRequest):
    """Public endpoint: Accept team invitation and complete account activation."""
    user = await OrgService.accept_invitation(
        raw_token=payload.token,
        full_name=payload.full_name,
        password=payload.password,
    )

    return UserSummaryResponse(
        id=str(user.id),
        org_id=user.org_id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        is_active=user.is_active,
    )
