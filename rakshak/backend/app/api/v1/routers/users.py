"""
Users router (/api/v1/users).
Team member listing, role assignment, and soft deletion.
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from beanie import PydanticObjectId

from app.core.deps import get_current_user, require_permission
from app.core.errors import NotFoundError, ForbiddenError, AppError
from app.models.user import User, utc_now
from app.repositories.repos import AuditRepository
from app.schemas.user import UserResponse, UserUpdateRequest

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("", response_model=List[UserResponse], dependencies=[Depends(require_permission("users:read"))])
async def list_users(
    current_user: User = Depends(get_current_user),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
):
    """List team members within current organization."""
    users = await User.find(
        User.org_id == current_user.org_id,
        User.deleted_at == None,
    ).skip(skip).limit(limit).to_list()

    return [
        UserResponse(
            id=str(u.id),
            org_id=u.org_id,
            email=u.email,
            full_name=u.full_name,
            role=u.role,
            is_active=u.is_active,
            created_at=u.created_at,
            last_login_at=u.last_login_at,
        )
        for u in users
    ]


@router.patch("/{user_id}", response_model=UserResponse, dependencies=[Depends(require_permission("users:manage"))])
async def update_user(
    user_id: str,
    payload: UserUpdateRequest,
    current_user: User = Depends(get_current_user),
):
    """Update team member role or active status. Cannot demote last owner."""
    user = await User.find_one({"_id": PydanticObjectId(user_id), "org_id": current_user.org_id})
    if not user or user.deleted_at is not None:
        raise NotFoundError("User", user_id)

    # Protect Owner role
    if payload.role:
        if payload.role == "owner" and current_user.role != "owner":
            raise ForbiddenError("Only an owner can grant the owner role.")
        if user.role == "owner" and payload.role != "owner":
            owners_count = await User.find({"org_id": current_user.org_id, "role": "owner", "deleted_at": None}).count()
            if owners_count <= 1:
                raise AppError("Cannot demote the last remaining owner in the organization.", status_code=400)
        user.role = payload.role

    if payload.is_active is not None:
        if user.role == "owner" and not payload.is_active:
            owners_count = await User.find({"org_id": current_user.org_id, "role": "owner", "deleted_at": None}).count()
            if owners_count <= 1:
                raise AppError("Cannot deactivate the last remaining owner in the organization.", status_code=400)
        user.is_active = payload.is_active

    await user.save()

    audit_repo = AuditRepository(current_user.org_id)
    await audit_repo.record_audit(
        actor={"type": "user", "id": str(current_user.id), "email": current_user.email},
        action="user.updated",
        target=f"user:{user.id}",
        reason=f"Updated user status (role={user.role}, active={user.is_active})",
    )

    return UserResponse(
        id=str(user.id),
        org_id=user.org_id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
    )


@router.delete("/{user_id}", dependencies=[Depends(require_permission("users:manage"))])
async def delete_user(user_id: str, current_user: User = Depends(get_current_user)):
    """Soft-delete team member. Cannot delete last owner or oneself."""
    user = await User.find_one({"_id": PydanticObjectId(user_id), "org_id": current_user.org_id})
    if not user or user.deleted_at is not None:
        raise NotFoundError("User", user_id)

    if str(user.id) == str(current_user.id):
        raise AppError("Cannot delete your own user account.", status_code=400)

    if user.role == "owner":
        owners_count = await User.find({"org_id": current_user.org_id, "role": "owner", "deleted_at": None}).count()
        if owners_count <= 1:
            raise AppError("Cannot delete the last remaining owner in the organization.", status_code=400)

    user.deleted_at = utc_now()
    user.is_active = False
    user.token_version += 1
    await user.save()

    audit_repo = AuditRepository(current_user.org_id)
    await audit_repo.record_audit(
        actor={"type": "user", "id": str(current_user.id), "email": current_user.email},
        action="user.deleted",
        target=f"user:{user.id}",
        reason=f"Soft-deleted user {user.email}.",
    )

    return {"message": "User deactivated successfully."}
