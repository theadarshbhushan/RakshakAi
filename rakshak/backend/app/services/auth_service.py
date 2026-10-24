"""
Authentication and Identity service for RakshakAI multi-tenant platform.
Implements Argon2id verification, account lockout protection, JWT access tokens,
refresh token family rotation, and reuse attack detection.
"""
from datetime import datetime, timedelta, timezone
import re
import uuid
import logging
from typing import Tuple, Optional, Dict, Any
from beanie import PydanticObjectId
import yaml

from app.core.config import settings
from app.core.security import (
    validate_password_strength,
    get_password_hash,
    verify_password,
    create_access_token,
    generate_opaque_token,
    hash_token,
)
from app.core.errors import UnauthorizedError, ConflictError, NotFoundError, AppError
from app.models.organization import Organization, Site
from app.models.user import User, RefreshSession, PasswordResetToken, utc_now
from app.models.rules import RuleDocument
from app.models.zone import Zone, Camera
from app.repositories.repos import AuditRepository
from app.schemas.auth import UserSummaryResponse

logger = logging.getLogger("rakshakai.services.auth")


def slugify(text: str) -> str:
    """Generate URL-safe slug from organization name."""
    s = text.lower().strip()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_-]+", "-", s)
    return s or "org"


class AuthService:
    @staticmethod
    async def register_organization(
        org_name: str,
        site_name: str,
        full_name: str,
        email: str,
        password: str,
        ip: Optional[str] = None,
        user_agent: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> Tuple[str, str, UserSummaryResponse]:
        """
        Register a new tenant organization with owner user, default site, rules, and zones.
        """
        norm_email = email.lower().strip()
        validate_password_strength(password)

        # Check existing user
        existing_user = await User.find_one(User.email == norm_email)
        if existing_user:
            raise ConflictError("An account with this email address already exists.", code="EMAIL_ALREADY_EXISTS")

        # Create Organization
        base_slug = slugify(org_name)
        slug = base_slug
        count = 1
        while await Organization.find_one(Organization.slug == slug):
            slug = f"{base_slug}-{count}"
            count += 1

        org = Organization(
            name=org_name.strip(),
            slug=slug,
            plan="free",
        )
        await org.insert()
        org_id = str(org.id)

        # Create Default Site
        site = Site(
            org_id=org_id,
            name=site_name.strip(),
            timezone="Asia/Kolkata",
        )
        await site.insert()
        site_id = str(site.id)

        # Load and seed default rules, zones, and cameras
        rules_data = {}
        if settings.RULES_DEFAULT_PATH.exists():
            with open(settings.RULES_DEFAULT_PATH, "r", encoding="utf-8") as rf:
                rules_data = yaml.safe_load(rf) or {}

        rule_doc = RuleDocument(
            org_id=org_id,
            version=1,
            curfew=rules_data.get("curfew", {}),
            zones=rules_data.get("zones", {}),
            tailgating=rules_data.get("tailgating", {}),
            fusion=rules_data.get("fusion", {}),
            weights=rules_data.get("weights", {}),
            updated_by="system_setup",
        )
        await rule_doc.insert()

        # Seed initial zones
        zones_config = rules_data.get("zones", {})
        for zid, zconf in zones_config.items():
            zone = Zone(
                org_id=org_id,
                site_id=site_id,
                zone_id=zid,
                name=zconf.get("name", zid.replace("_", " ").title()),
                type=zconf.get("type", "common"),
                allowed_roles=zconf.get("allowed_roles", []),
                adjacent_zone_ids=zconf.get("adjacent_zone_ids", []),
            )
            await zone.insert()

        # Seed initial cameras
        cameras_config = rules_data.get("cameras", [])
        for cconf in cameras_config:
            cam = Camera(
                org_id=org_id,
                site_id=site_id,
                camera_id=cconf.get("camera_id"),
                name=cconf.get("name", cconf.get("camera_id")),
                zone_id=cconf.get("zone_id"),
                source_path=cconf.get("source_path", ""),
                door_line=cconf.get("door_line"),
            )
            await cam.insert()

        # Create Owner User
        hashed_pw = get_password_hash(password)
        user = User(
            org_id=org_id,
            email=norm_email,
            full_name=full_name.strip(),
            password_hash=hashed_pw,
            role="owner",
            is_active=True,
            token_version=1,
            last_login_at=utc_now(),
        )
        await user.insert()
        user_id = str(user.id)

        # Issue refresh token in new family
        raw_refresh = generate_opaque_token()
        family_id = str(uuid.uuid4())
        session = RefreshSession(
            org_id=org_id,
            user_id=user_id,
            family_id=family_id,
            token_hash=hash_token(raw_refresh),
            user_agent=user_agent,
            ip=ip,
            expires_at=utc_now() + timedelta(days=settings.REFRESH_TOKEN_TTL_DAYS),
        )
        await session.insert()

        # Issue access token
        access_token = create_access_token(
            user_id=user_id,
            org_id=org_id,
            role="owner",
            token_version=user.token_version,
        )

        # Record audit log
        audit_repo = AuditRepository(org_id)
        await audit_repo.record_audit(
            actor={"type": "user", "id": user_id, "email": norm_email},
            action="auth.register_organization",
            target=f"organization:{org_id}",
            reason=f"Registered organization '{org_name}' with owner '{norm_email}'",
            ip=ip,
            user_agent=user_agent,
            request_id=request_id,
        )

        user_summary = UserSummaryResponse(
            id=user_id,
            org_id=org_id,
            email=norm_email,
            full_name=user.full_name,
            role=user.role,
            is_active=user.is_active,
        )

        return access_token, raw_refresh, user_summary

    @staticmethod
    async def login(
        email: str,
        password: str,
        ip: Optional[str] = None,
        user_agent: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> Tuple[str, str, UserSummaryResponse]:
        """
        Authenticate user with brute-force lockout protection and issue tokens.
        """
        norm_email = email.lower().strip()
        user = await User.find_one(User.email == norm_email)

        # Constant-time dummy verify if user does not exist
        if not user or user.deleted_at is not None:
            verify_password(password, "$argon2id$v=19$m=65536,t=3,p=4$dummyhashdummypassword12345$dummyhash")
            raise UnauthorizedError("Invalid email or password", code="AUTH_INVALID_CREDENTIALS")

        audit_repo = AuditRepository(user.org_id)

        # Check account lockout
        now = utc_now()
        if user.locked_until and user.locked_until > now:
            remaining_mins = int((user.locked_until - now).total_seconds() / 60) + 1
            raise UnauthorizedError(
                f"Account is temporarily locked due to too many failed attempts. Try again in {remaining_mins} minutes.",
                code="AUTH_ACCOUNT_LOCKED",
            )

        # Verify password
        if not verify_password(password, user.password_hash):
            user.failed_login_count += 1
            if user.failed_login_count >= 5:
                user.locked_until = now + timedelta(minutes=15)
                await audit_repo.record_audit(
                    actor={"type": "user", "id": str(user.id), "email": norm_email},
                    action="auth.account_locked",
                    target=f"user:{user.id}",
                    reason="Locked account for 15 min after 5 consecutive failed login attempts.",
                    ip=ip,
                    user_agent=user_agent,
                    request_id=request_id,
                )
            await audit_repo.record_audit(
                actor={"type": "user", "id": str(user.id), "email": norm_email},
                action="auth.login_failed",
                target=f"user:{user.id}",
                reason=f"Failed login attempt ({user.failed_login_count}/5).",
                ip=ip,
                user_agent=user_agent,
                request_id=request_id,
            )
            await user.save()
            raise UnauthorizedError("Invalid email or password", code="AUTH_INVALID_CREDENTIALS")

        if not user.is_active:
            raise UnauthorizedError("Account is deactivated. Please contact an organization administrator.", code="AUTH_USER_DISABLED")

        # Login successful: reset failed attempts
        user.failed_login_count = 0
        user.locked_until = None
        user.last_login_at = now
        await user.save()

        # Create refresh session family
        raw_refresh = generate_opaque_token()
        family_id = str(uuid.uuid4())
        session = RefreshSession(
            org_id=user.org_id,
            user_id=str(user.id),
            family_id=family_id,
            token_hash=hash_token(raw_refresh),
            user_agent=user_agent,
            ip=ip,
            expires_at=now + timedelta(days=settings.REFRESH_TOKEN_TTL_DAYS),
        )
        await session.insert()

        access_token = create_access_token(
            user_id=str(user.id),
            org_id=user.org_id,
            role=user.role,
            token_version=user.token_version,
        )

        await audit_repo.record_audit(
            actor={"type": "user", "id": str(user.id), "email": norm_email},
            action="auth.login",
            target=f"user:{user.id}",
            reason="User logged in successfully.",
            ip=ip,
            user_agent=user_agent,
            request_id=request_id,
        )

        user_summary = UserSummaryResponse(
            id=str(user.id),
            org_id=user.org_id,
            email=user.email,
            full_name=user.full_name,
            role=user.role,
            is_active=user.is_active,
        )

        return access_token, raw_refresh, user_summary

    @staticmethod
    async def refresh_token(
        raw_token: str,
        ip: Optional[str] = None,
        user_agent: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> Tuple[str, str, UserSummaryResponse]:
        """
        Rotate refresh token. Detects reuse attacks and invalidates compromised token family.
        """
        token_h = hash_token(raw_token)
        session = await RefreshSession.find_one(RefreshSession.token_hash == token_h)

        if not session:
            raise UnauthorizedError("Invalid refresh token", code="AUTH_INVALID_TOKEN")

        audit_repo = AuditRepository(session.org_id)
        now = utc_now()

        # Reuse Detection: If already revoked or replaced, revoke entire family!
        if session.revoked_at is not None or session.expires_at < now:
            logger.warning(f"Refresh token reuse detected for family {session.family_id}!")
            await RefreshSession.find({"family_id": session.family_id}).update(
                {"$set": {"revoked_at": now}}
            )
            await audit_repo.record_audit(
                actor={"type": "user", "id": session.user_id},
                action="auth.refresh_reuse_detected",
                target=f"session_family:{session.family_id}",
                reason="Revoked refresh token family due to suspected token replay/theft.",
                ip=ip,
                user_agent=user_agent,
                request_id=request_id,
            )
            raise UnauthorizedError("Compromised or expired refresh token", code="AUTH_TOKEN_REVOKED")

        # Invalidate old token
        new_raw_refresh = generate_opaque_token()
        new_token_h = hash_token(new_raw_refresh)
        session.revoked_at = now
        session.replaced_by = new_token_h
        await session.save()

        # Issue new token in same family
        new_session = RefreshSession(
            org_id=session.org_id,
            user_id=session.user_id,
            family_id=session.family_id,
            token_hash=new_token_h,
            user_agent=user_agent,
            ip=ip,
            expires_at=now + timedelta(days=settings.REFRESH_TOKEN_TTL_DAYS),
        )
        await new_session.insert()

        # Retrieve user to check status and current token_version
        user = await User.get(PydanticObjectId(session.user_id))
        if not user or not user.is_active or user.deleted_at is not None:
            raise UnauthorizedError("User is no longer active", code="AUTH_USER_DISABLED")

        access_token = create_access_token(
            user_id=str(user.id),
            org_id=user.org_id,
            role=user.role,
            token_version=user.token_version,
        )

        user_summary = UserSummaryResponse(
            id=str(user.id),
            org_id=user.org_id,
            email=user.email,
            full_name=user.full_name,
            role=user.role,
            is_active=user.is_active,
        )

        return access_token, new_raw_refresh, user_summary

    @staticmethod
    async def logout(raw_refresh: Optional[str]) -> None:
        """Revoke refresh session family."""
        if raw_refresh:
            token_h = hash_token(raw_refresh)
            session = await RefreshSession.find_one(RefreshSession.token_hash == token_h)
            if session:
                now = utc_now()
                await RefreshSession.find({"family_id": session.family_id}).update(
                    {"$set": {"revoked_at": now}}
                )

    @staticmethod
    async def logout_all(user: User) -> None:
        """Increment token_version to immediately invalidate all access tokens and refresh sessions."""
        user.token_version += 1
        await user.save()
        now = utc_now()
        await RefreshSession.find({"user_id": str(user.id)}).update(
            {"$set": {"revoked_at": now}}
        )
