"""
FastAPI dependencies for authentication, multi-tenancy, RBAC, and machine API keys.
"""
from typing import Any, Dict, Optional

from beanie import PydanticObjectId
from fastapi import Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer, OAuth2PasswordBearer

from app.core.errors import ForbiddenError, NotFoundError, UnauthorizedError
from app.core.permissions import has_permission
from app.core.security import decode_access_token, hash_token
from app.models.organization import Organization
from app.models.user import ApiKey, User, utc_now

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token", auto_error=False)
http_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    token: Optional[str] = Depends(oauth2_scheme),
    bearer: Optional[HTTPAuthorizationCredentials] = Depends(http_bearer),
) -> User:
    """
    Validate bearer JWT token and return active User document.
    Supports either OAuth2 password flow token, HTTPBearer authorization header,
    auth_token query parameter, or access_token cookie (for media tags).
    Enforces token_version check, active status, and tenant binding.
    """
    q_token = request.query_params.get("auth_token")
    if not q_token:
        # If token is in query params and contains JWT dots, allow it
        raw_token = request.query_params.get("token")
        if raw_token and "." in raw_token:
            q_token = raw_token

    cookie_token = request.cookies.get("access_token")

    auth_token = token or (bearer.credentials if bearer else None) or q_token or cookie_token
    if not auth_token:
        raise UnauthorizedError("Missing authentication token", code="AUTH_MISSING_TOKEN")

    payload = decode_access_token(auth_token)
    user_id = payload.get("sub")
    org_id = payload.get("org_id")
    token_version = payload.get("tv")

    if not user_id or not org_id:
        raise UnauthorizedError("Invalid token claims", code="AUTH_INVALID_TOKEN")

    try:
        user = await User.get(PydanticObjectId(user_id))
    except Exception:
        user = await User.find_one({"_id": user_id})

    if not user or user.org_id != org_id:
        raise UnauthorizedError("User does not exist or organization mismatch", code="AUTH_USER_NOT_FOUND")

    if not user.is_active or user.deleted_at is not None:
        raise UnauthorizedError("User account is inactive or disabled", code="AUTH_USER_DISABLED")

    # Invalidate token if token_version was incremented (e.g. via logout-all)
    if user.token_version != token_version:
        raise UnauthorizedError("Session has been revoked", code="AUTH_TOKEN_REVOKED")

    return user


async def get_current_org(current_user: User = Depends(get_current_user)) -> Organization:
    """
    Retrieve Organization document for current authenticated user.
    """
    try:
        org = await Organization.get(PydanticObjectId(current_user.org_id))
    except Exception:
        org = await Organization.find_one({"_id": current_user.org_id})

    if not org:
        raise NotFoundError("Organization", current_user.org_id)
    return org


def require_permission(permission: str):
    """
    Enforce granular RBAC permission based on current user role.
    """
    async def permission_checker(current_user: User = Depends(get_current_user)) -> User:
        if not has_permission(current_user.role, permission):
            raise ForbiddenError(
                f"Permission '{permission}' required. Your role '{current_user.role}' lacks sufficient privileges."
            )
        return current_user

    return permission_checker


async def get_api_key_principal(x_api_key: Optional[str] = Header(None, alias="X-API-Key")) -> Optional[Dict[str, Any]]:
    """
    Authenticate edge devices via X-API-Key header: rk_live_<prefix>_<secret>.
    """
    if not x_api_key:
        return None

    if not x_api_key.startswith("rk_live_"):
        raise UnauthorizedError("Malformed API key format", code="AUTH_INVALID_API_KEY")

    parts = x_api_key.split("_")
    if len(parts) < 4:
        raise UnauthorizedError("Invalid API key format", code="AUTH_INVALID_API_KEY")

    prefix = parts[2]
    secret = "_".join(parts[3:])
    secret_hash = hash_token(secret)

    api_key_doc = await ApiKey.find_one(ApiKey.prefix == prefix)
    if not api_key_doc or api_key_doc.secret_hash != secret_hash:
        raise UnauthorizedError("Invalid or unknown API key", code="AUTH_INVALID_API_KEY")

    if api_key_doc.revoked_at is not None:
        raise UnauthorizedError("API key has been revoked", code="AUTH_API_KEY_REVOKED")

    # Update last used timestamp
    api_key_doc.last_used_at = utc_now()
    await api_key_doc.save()

    return {
        "type": "api_key",
        "org_id": api_key_doc.org_id,
        "key_id": str(api_key_doc.id),
        "name": api_key_doc.name,
        "scopes": api_key_doc.scopes,
        "site_id": api_key_doc.site_id,
    }


async def get_ingest_principal(
    api_key_principal: Optional[Dict[str, Any]] = Depends(get_api_key_principal),
    token: Optional[str] = Depends(oauth2_scheme),
    bearer: Optional[HTTPAuthorizationCredentials] = Depends(http_bearer),
) -> Dict[str, Any]:
    """
    Principal dependency for signal ingestion.
    Accepts either a valid API Key with 'signals:write' scope OR an authenticated User with 'signals:write' permission.
    """
    if api_key_principal:
        if "signals:write" not in api_key_principal.get("scopes", []):
            raise ForbiddenError("API key lacks required 'signals:write' scope.")
        return api_key_principal

    auth_token = token or (bearer.credentials if bearer else None)
    if auth_token:
        user = await get_current_user(token=token, bearer=bearer)
        if not has_permission(user.role, "signals:write"):
            raise ForbiddenError("User role lacks required 'signals:write' permission.")
        return {
            "type": "user",
            "org_id": user.org_id,
            "user_id": str(user.id),
            "email": user.email,
            "role": user.role,
        }

    raise UnauthorizedError("Authentication required (X-API-Key or Bearer token)", code="AUTH_REQUIRED")

