"""
Authentication Router (/api/v1/auth).
Handles organization registration, login with rate-limiting & brute force lockout,
refresh rotation with reuse detection, logout, password change, and sessions.
"""
import logging
from typing import List

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, Request, Response, status

from app.core.config import settings
from app.core.deps import get_current_user
from app.core.errors import AppError, NotFoundError, UnauthorizedError
from app.core.permissions import get_permissions_for_role
from app.core.rate_limit import limiter
from app.core.security import get_password_hash, hash_token, validate_password_strength, verify_password
from app.models.organization import Organization
from app.models.user import PasswordResetToken, RefreshSession, User, utc_now
from app.repositories.repos import AuditRepository
from app.schemas.auth import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    RegisterOrgRequest,
    ResetPasswordRequest,
    SessionResponse,
    TokenResponse,
)
from app.schemas.user import MeResponse
from app.services.auth_service import AuthService

logger = logging.getLogger("rakshakai.auth")

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register-organization", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register_organization(payload: RegisterOrgRequest, request: Request, response: Response):
    """
    Register a new tenant organization (plan: free), default site, and owner user.
    Sets refresh token in secure httpOnly cookie and returns access token.
    """
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("User-Agent")
    request_id = getattr(request.state, "request_id", None)

    access_token, raw_refresh, user_summary = await AuthService.register_organization(
        org_name=payload.org_name,
        site_name=payload.site_name,
        full_name=payload.full_name,
        email=payload.email,
        password=payload.password,
        ip=client_ip,
        user_agent=user_agent,
        request_id=request_id,
    )

    # Set httpOnly cookie for refresh token
    response.set_cookie(
        key="rakshak_refresh",
        value=raw_refresh,
        httponly=True,
        secure=(settings.ENV == "prod"),
        samesite="lax",
        path="/api/v1/auth",
        max_age=settings.REFRESH_TOKEN_TTL_DAYS * 86400,
    )

    dev_refresh = raw_refresh if settings.ENV in ("dev", "test") else None
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_TTL_MIN * 60,
        user=user_summary,
        refresh_token=dev_refresh,
    )


@router.post("/login", response_model=TokenResponse)
@limiter.limit(settings.RATE_LIMIT_LOGIN)
async def login(payload: LoginRequest, request: Request, response: Response):
    """
    Authenticate user with Argon2id and rate limiting.
    Locks account for 15 minutes after 5 consecutive failed attempts.
    """
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("User-Agent")
    request_id = getattr(request.state, "request_id", None)

    access_token, raw_refresh, user_summary = await AuthService.login(
        email=payload.email,
        password=payload.password,
        ip=client_ip,
        user_agent=user_agent,
        request_id=request_id,
    )

    response.set_cookie(
        key="rakshak_refresh",
        value=raw_refresh,
        httponly=True,
        secure=(settings.ENV == "prod"),
        samesite="lax",
        path="/api/v1/auth",
        max_age=settings.REFRESH_TOKEN_TTL_DAYS * 86400,
    )

    dev_refresh = raw_refresh if settings.ENV in ("dev", "test") else None
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_TTL_MIN * 60,
        user=user_summary,
        refresh_token=dev_refresh,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(request: Request, response: Response):
    """
    Rotate refresh token. Invalidates presented refresh token and issues a new one in the same family.
    Replay of a revoked refresh token triggers reuse detection and revokes the whole family.
    """
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("User-Agent")
    request_id = getattr(request.state, "request_id", None)

    # Check explicit Authorization header or X-Refresh-Token first, then fallback to cookie
    raw_token = None
    auth_hdr = request.headers.get("Authorization")
    if auth_hdr and auth_hdr.startswith("Bearer "):
        raw_token = auth_hdr.split(" ")[1]
    if not raw_token:
        raw_token = request.headers.get("X-Refresh-Token")
    if not raw_token:
        raw_token = request.cookies.get("rakshak_refresh")
    if not raw_token:
        try:
            body = await request.json()
            if isinstance(body, dict):
                raw_token = body.get("refresh_token")
        except Exception:
            pass

    if not raw_token:
        raise UnauthorizedError("Missing refresh token", code="AUTH_MISSING_TOKEN")

    access_token, new_raw_refresh, user_summary = await AuthService.refresh_token(
        raw_token=raw_token,
        ip=client_ip,
        user_agent=user_agent,
        request_id=request_id,
    )

    response.set_cookie(
        key="rakshak_refresh",
        value=new_raw_refresh,
        httponly=True,
        secure=(settings.ENV == "prod"),
        samesite="lax",
        path="/api/v1/auth",
        max_age=settings.REFRESH_TOKEN_TTL_DAYS * 86400,
    )

    dev_refresh = new_raw_refresh if settings.ENV in ("dev", "test") else None
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_TTL_MIN * 60,
        user=user_summary,
        refresh_token=dev_refresh,
    )


@router.post("/logout")
async def logout(request: Request, response: Response):
    """Log out of current session and revoke refresh token family."""
    raw_token = request.cookies.get("rakshak_refresh")
    await AuthService.logout(raw_token)
    response.delete_cookie("rakshak_refresh", path="/api/v1/auth")
    return {"message": "Logged out successfully"}


@router.post("/logout-all")
async def logout_all(current_user: User = Depends(get_current_user), response: Response = None):
    """Increment token_version to invalidate all active JWTs and refresh sessions across all devices."""
    await AuthService.logout_all(current_user)
    if response:
        response.delete_cookie("rakshak_refresh", path="/api/v1/auth")
    return {"message": "All sessions have been revoked."}


@router.get("/me", response_model=MeResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """Retrieve authenticated user profile, resolved permission list, and organization plan summary."""
    org = await Organization.get(PydanticObjectId(current_user.org_id))
    if not org:
        raise NotFoundError("Organization", current_user.org_id)

    permissions = get_permissions_for_role(current_user.role)

    return MeResponse(
        id=str(current_user.id),
        email=current_user.email,
        full_name=current_user.full_name,
        role=current_user.role,
        permissions=permissions,
        org_id=str(org.id),
        org_name=org.name,
        org_slug=org.slug,
        plan=org.plan,
        settings=org.settings,
    )


@router.post("/change-password")
async def change_password(payload: ChangePasswordRequest, current_user: User = Depends(get_current_user)):
    """Change account password. Requires verification of current password."""
    if not verify_password(payload.current_password, current_user.password_hash):
        raise UnauthorizedError("Current password is incorrect.", code="AUTH_INVALID_CREDENTIALS")

    validate_password_strength(payload.new_password)
    current_user.password_hash = get_password_hash(payload.new_password)
    current_user.token_version += 1
    await current_user.save()

    audit_repo = AuditRepository(current_user.org_id)
    await audit_repo.record_audit(
        actor={"type": "user", "id": str(current_user.id), "email": current_user.email},
        action="auth.password_changed",
        target=f"user:{current_user.id}",
        reason="User updated account password.",
    )

    return {"message": "Password updated successfully. Other sessions have been revoked."}


# =============================================================================
# TODO [STABILIZATION]: The endpoints below are disabled during stabilization.
# Password reset and session listing will be re-enabled in a future phase.
# =============================================================================
# @router.post("/forgot-password")
# @limiter.limit("5/minute")
# async def forgot_password(payload: ForgotPasswordRequest, request: Request): ...
#
# @router.post("/reset-password")
# async def reset_password(payload: ResetPasswordRequest): ...
#
# @router.get("/sessions", response_model=List[SessionResponse])
# async def list_sessions(current_user: User = Depends(get_current_user)): ...
#
# @router.delete("/sessions/{session_id}")
# async def revoke_session(session_id: str, current_user: User = Depends(get_current_user)): ...

