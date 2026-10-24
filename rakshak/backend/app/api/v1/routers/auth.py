"""
Authentication Router (/api/v1/auth).
Handles organization registration, login with rate-limiting & brute force lockout,
refresh rotation with reuse detection, logout, password change, and sessions.
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, Request, Response, status
from beanie import PydanticObjectId

from app.core.config import settings
from app.core.rate_limit import limiter
from app.core.deps import get_current_user, require_permission
from app.core.security import validate_password_strength, get_password_hash, verify_password, hash_token
from app.core.errors import UnauthorizedError, AppError, NotFoundError
from app.models.user import User, RefreshSession, PasswordResetToken, utc_now
from app.models.organization import Organization
from app.repositories.repos import AuditRepository
from app.services.auth_service import AuthService
from app.schemas.auth import (
    RegisterOrgRequest,
    LoginRequest,
    TokenResponse,
    ChangePasswordRequest,
    ForgotPasswordRequest,
    ResetPasswordRequest,
    SessionResponse,
    UserSummaryResponse,
)
from app.schemas.user import MeResponse
from app.core.permissions import get_permissions_for_role

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

    dev_refresh = raw_refresh if settings.ENV == "dev" else None
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

    dev_refresh = raw_refresh if settings.ENV == "dev" else None
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

    # Check cookie first, fallback to Authorization header or query param
    raw_token = request.cookies.get("rakshak_refresh")
    if not raw_token:
        auth_hdr = request.headers.get("Authorization")
        if auth_hdr and auth_hdr.startswith("Bearer "):
            raw_token = auth_hdr.split(" ")[1]

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

    dev_refresh = new_raw_refresh if settings.ENV == "dev" else None
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


@router.post("/forgot-password")
@limiter.limit("5/minute")
async def forgot_password(payload: ForgotPasswordRequest, request: Request):
    """
    Generate password reset token. Always returns 200 to prevent user enumeration.
    Logs the reset link in development mode.
    """
    user = await User.find_one(User.email == payload.email.lower().strip())
    if user and user.is_active:
        raw_token = AuthService.generate_opaque_token() if hasattr(AuthService, "generate_opaque_token") else hash_token(payload.email)
        import secrets
        raw_token = secrets.token_urlsafe(32)
        token_doc = PasswordResetToken(
            org_id=user.org_id,
            user_id=str(user.id),
            token_hash=hash_token(raw_token),
            expires_at=utc_now() + __import__("datetime").timedelta(minutes=30),
        )
        await token_doc.insert()
        logger.info(f"[DEV NOTIFICATION] Password reset link for {user.email}: {settings.FRONTEND_URL}/reset-password?token={raw_token}")

    return {"message": "If an account with that email exists, password reset instructions have been sent."}


@router.post("/reset-password")
async def reset_password(payload: ResetPasswordRequest):
    """Reset password using single-use 30-minute token."""
    token_h = hash_token(payload.token)
    reset_doc = await PasswordResetToken.find_one(PasswordResetToken.token_hash == token_h)

    now = utc_now()
    if not reset_doc or reset_doc.used_at is not None or reset_doc.expires_at < now:
        raise AppError("Password reset token is invalid or has expired.", code="AUTH_INVALID_TOKEN", status_code=400)

    validate_password_strength(payload.new_password)
    user = await User.get(PydanticObjectId(reset_doc.user_id))
    if not user:
        raise NotFoundError("User", reset_doc.user_id)

    user.password_hash = get_password_hash(payload.new_password)
    user.token_version += 1
    await user.save()

    reset_doc.used_at = now
    await reset_doc.save()

    return {"message": "Password has been successfully reset. Please log in with your new password."}


@router.get("/sessions", response_model=List[SessionResponse])
async def list_sessions(current_user: User = Depends(get_current_user)):
    """List active refresh sessions for authenticated user."""
    sessions = await RefreshSession.find(
        RefreshSession.user_id == str(current_user.id),
        RefreshSession.revoked_at == None,
        RefreshSession.expires_at > utc_now(),
    ).to_list()

    return [
        SessionResponse(
            id=str(s.id),
            user_agent=s.user_agent,
            ip=s.ip,
            created_at=s.created_at,
            last_used_at=s.last_used_at,
            expires_at=s.expires_at,
        )
        for s in sessions
    ]


@router.delete("/sessions/{session_id}")
async def revoke_session(session_id: str, current_user: User = Depends(get_current_user)):
    """Revoke a specific active refresh session."""
    session = await RefreshSession.find_one(
        RefreshSession.id == PydanticObjectId(session_id),
        RefreshSession.user_id == str(current_user.id),
    )
    if not session:
        raise NotFoundError("Session", session_id)

    session.revoked_at = utc_now()
    await session.save()
    return {"message": "Session revoked."}
