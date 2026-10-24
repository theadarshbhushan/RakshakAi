"""
Privacy and Pseudonymization Module for RakshakAI.
Strictly ensures raw card IDs and personal identifiers never leave the backend.
Salted SHA-256 is used for irreversibly pseudonymizing credentials.
"""
import hashlib
from typing import Any, Optional

from app.core.config import settings


def generate_pseudo_id(raw_id: str, salt: Optional[str] = None) -> str:
    """
    Generate an 8-character salted SHA-256 pseudonym for an access card or identifier.
    The salt is securely retrieved from configuration.
    """
    if not raw_id:
        return "anon0000"
    actual_salt = salt or settings.PSEUDONYM_SALT
    salted_bytes = f"{actual_salt}:{raw_id}".encode("utf-8")
    return hashlib.sha256(salted_bytes).hexdigest()[:8]


def sanitize_for_api(data: Any) -> Any:
    """
    Recursively sanitize dictionaries and lists before returning in API responses.
    Strips raw 'card_id', 'password_hash', etc., and preserves only pseudonymized IDs.
    """
    if isinstance(data, dict):
        cleaned = {}
        for k, v in data.items():
            if k in ("password_hash", "token_hash"):
                continue  # Never expose password or token hashes in API
            if k == "card_id":
                cleaned["pseudo_id"] = generate_pseudo_id(str(v))
            else:
                cleaned[k] = sanitize_for_api(v)
        return cleaned
    elif isinstance(data, list):
        return [sanitize_for_api(item) for item in data]
    return data
