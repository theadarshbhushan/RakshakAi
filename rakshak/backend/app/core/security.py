"""
Cryptographic security module for RakshakAI.
Handles Argon2id password hashing, password strength validation,
JWT access tokens, opaque refresh tokens, and API key generation.
"""
from datetime import datetime, timedelta, timezone
import hashlib
import re
import secrets
import uuid
from typing import Dict, Any, Optional, Tuple
import jwt
from pwdlib import PasswordHash
from app.core.config import settings
from app.core.errors import UnauthorizedError, AppError

pwd_hasher = PasswordHash.recommended()

COMMON_PASSWORDS = {
    "password", "12345678", "123456789", "1234567890", "password123", "password1",
    "admin1234", "admin12345", "welcome123", "qwertyuiop", "qwerty1234", "letmein123",
    "iloveyou123", "monkey1234", "dragon1234", "master1234", "sunshine12", "princess12",
    "football12", "baseball12", "superman12", "trustno123", "shadow1234", "secret1234",
}


def validate_password_strength(password: str) -> None:
    """Enforce minimum 10 characters, at least one letter and digit, not in common list."""
    if len(password) < 10:
        raise AppError(
            message="Password must be at least 10 characters long.",
            code="WEAK_PASSWORD",
            status_code=400,
        )
    if not re.search(r"[A-Za-z]", password):
        raise AppError(
            message="Password must contain at least one letter.",
            code="WEAK_PASSWORD",
            status_code=400,
        )
    if not re.search(r"\d", password):
        raise AppError(
            message="Password must contain at least one numeric digit.",
            code="WEAK_PASSWORD",
            status_code=400,
        )
    if password.lower() in COMMON_PASSWORDS:
        raise AppError(
            message="Password is too common and easily guessed. Please select a stronger password.",
            code="WEAK_PASSWORD",
            status_code=400,
        )


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify plain password against stored Argon2id hash."""
    return pwd_hasher.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Generate Argon2id password hash."""
    return pwd_hasher.hash(password)


def create_access_token(
    user_id: str,
    org_id: str,
    role: str,
    token_version: int,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Generate signed JWT access token.
    Claims: sub, org_id, role, tv, jti, type, iat, exp, iss, aud
    """
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_TTL_MIN))
    payload = {
        "sub": str(user_id),
        "org_id": str(org_id),
        "role": role,
        "tv": token_version,
        "jti": str(uuid.uuid4()),
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> Dict[str, Any]:
    """
    Decode and validate JWT access token signature, exp, iss, aud, and type.
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
            issuer=settings.JWT_ISSUER,
            audience=settings.JWT_AUDIENCE,
        )
        if payload.get("type") != "access":
            raise UnauthorizedError(message="Invalid token type", code="AUTH_INVALID_TOKEN")
        return payload
    except jwt.ExpiredSignatureError:
        raise UnauthorizedError(message="Token has expired", code="AUTH_TOKEN_EXPIRED")
    except jwt.InvalidTokenError as exc:
        raise UnauthorizedError(message=f"Invalid token: {exc}", code="AUTH_INVALID_TOKEN")


def generate_opaque_token() -> str:
    """Generate secure 256-bit random URL-safe string for refresh/invitation tokens."""
    return secrets.token_urlsafe(32)


def hash_token(raw_token: str) -> str:
    """Compute SHA-256 hash of a raw token for database storage."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def generate_api_key(prefix_length: int = 8) -> Tuple[str, str, str]:
    """
    Generate an edge device API key formatted as: rk_live_<prefix>_<secret>.
    Returns (full_key, prefix, secret_hash).
    """
    prefix = secrets.token_hex(prefix_length // 2)
    secret = secrets.token_urlsafe(24)
    full_key = f"rk_live_{prefix}_{secret}"
    secret_hash = hash_token(secret)
    return full_key, prefix, secret_hash
