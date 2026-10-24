"""
Tenant organization management, SaaS plan enforcement, invitations, and API keys.
"""
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional, Tuple
from beanie import PydanticObjectId

from app.core.security import (
    validate_password_strength,
    get_password_hash,
    generate_opaque_token,
    hash_token,
    generate_api_key,
)
from app.core.errors import PlanLimitReachedError, ConflictError, NotFoundError, AppError
from app.models.organization import Organization, Site
from app.models.zone import Zone, Camera
from app.models.user import User, Invitation, ApiKey, utc_now
from app.repositories.repos import AuditRepository

PLANS: Dict[str, Dict[str, Any]] = {
    "free": {
        "max_sites": 1,
        "max_cameras": 4,
        "max_users": 5,
        "retention_days_max": 7,
        "breakglass": True,
    },
    "pro": {
        "max_sites": 10,
        "max_cameras": 50,
        "max_users": 50,
        "retention_days_max": 30,
        "breakglass": True,
    },
    "enterprise": {
        "max_sites": 99999,
        "max_cameras": 99999,
        "max_users": 99999,
        "retention_days_max": 365,
        "breakglass": True,
    },
}


class OrgService:
    @staticmethod
    async def get_plan_limits(plan_name: str) -> Dict[str, Any]:
        return PLANS.get(plan_name, PLANS["free"])

    @staticmethod
    async def check_plan_limit(org_id: str, resource_type: str) -> None:
        """Enforce strict quota limits based on the organization's subscription plan."""
        org = await Organization.get(PydanticObjectId(org_id))
        if not org:
            raise NotFoundError("Organization", org_id)

        limits = await OrgService.get_plan_limits(org.plan)

        if resource_type == "site":
            current_count = await Site.find(Site.org_id == org_id).count()
            max_limit = limits.get("max_sites", 1)
            if current_count >= max_limit:
                raise PlanLimitReachedError(
                    f"Plan limit reached: '{org.plan}' plan allows a maximum of {max_limit} site(s). Please upgrade.",
                    details={"resource": "site", "current": current_count, "limit": max_limit, "plan": org.plan},
                )

        elif resource_type == "camera":
            current_count = await Camera.find(Camera.org_id == org_id).count()
            max_limit = limits.get("max_cameras", 4)
            if current_count >= max_limit:
                raise PlanLimitReachedError(
                    f"Plan limit reached: '{org.plan}' plan allows a maximum of {max_limit} camera(s). Please upgrade.",
                    details={"resource": "camera", "current": current_count, "limit": max_limit, "plan": org.plan},
                )

        elif resource_type == "user":
            current_count = await User.find(User.org_id == org_id, User.deleted_at == None).count()
            max_limit = limits.get("max_users", 5)
            if current_count >= max_limit:
                raise PlanLimitReachedError(
                    f"Plan limit reached: '{org.plan}' plan allows a maximum of {max_limit} team user(s). Please upgrade.",
                    details={"resource": "user", "current": current_count, "limit": max_limit, "plan": org.plan},
                )

    @staticmethod
    async def create_invitation(
        org_id: str,
        email: str,
        role: str,
        actor: User,
    ) -> Tuple[Invitation, str]:
        """Issue team invitation with a 72-hour single-use token."""
        await OrgService.check_plan_limit(org_id, "user")
        norm_email = email.lower().strip()

        # Check existing user
        if await User.find_one(User.email == norm_email):
            raise ConflictError("User with this email already exists.", code="USER_ALREADY_EXISTS")

        raw_token = generate_opaque_token()
        invitation = Invitation(
            org_id=org_id,
            email=norm_email,
            role=role,
            token_hash=hash_token(raw_token),
            created_by=str(actor.id),
            expires_at=utc_now() + timedelta(hours=72),
        )
        await invitation.insert()

        audit_repo = AuditRepository(org_id)
        await audit_repo.record_audit(
            actor={"type": "user", "id": str(actor.id), "email": actor.email},
            action="invitation.created",
            target=f"invitation:{invitation.id}",
            reason=f"Invited '{norm_email}' as '{role}'.",
        )

        return invitation, raw_token

    @staticmethod
    async def accept_invitation(
        raw_token: str,
        full_name: str,
        password: str,
    ) -> User:
        """Accept team invitation and activate user account."""
        validate_password_strength(password)
        token_h = hash_token(raw_token)
        invitation = await Invitation.find_one(Invitation.token_hash == token_h)

        if not invitation:
            raise NotFoundError("Invitation token is invalid or does not exist.")

        now = utc_now()
        if invitation.accepted_at is not None or invitation.expires_at < now:
            raise AppError("Invitation token has expired or already been used.", code="INVITATION_EXPIRED", status_code=400)

        # Create user
        user = User(
            org_id=invitation.org_id,
            email=invitation.email,
            full_name=full_name.strip(),
            password_hash=get_password_hash(password),
            role=invitation.role,
            is_active=True,
            token_version=1,
        )
        await user.insert()

        invitation.accepted_at = now
        await invitation.save()

        audit_repo = AuditRepository(invitation.org_id)
        await audit_repo.record_audit(
            actor={"type": "user", "id": str(user.id), "email": user.email},
            action="invitation.accepted",
            target=f"user:{user.id}",
            reason="Accepted invitation and created user account.",
        )

        return user

    @staticmethod
    async def create_api_key(
        org_id: str,
        name: str,
        scopes: List[str],
        site_id: Optional[str],
        actor: User,
    ) -> Tuple[ApiKey, str]:
        """Generate API key formatted as: rk_live_<prefix>_<secret>. Returns raw key once."""
        full_key, prefix, secret_hash = generate_api_key()

        api_key_doc = ApiKey(
            org_id=org_id,
            name=name.strip(),
            prefix=prefix,
            secret_hash=secret_hash,
            scopes=scopes,
            site_id=site_id,
            created_by=str(actor.id),
        )
        await api_key_doc.insert()

        audit_repo = AuditRepository(org_id)
        await audit_repo.record_audit(
            actor={"type": "user", "id": str(actor.id), "email": actor.email},
            action="api_key.created",
            target=f"api_key:{api_key_doc.id}",
            reason=f"Created API key '{name}' with prefix '{prefix}' and scopes {scopes}.",
        )

        return api_key_doc, full_key
