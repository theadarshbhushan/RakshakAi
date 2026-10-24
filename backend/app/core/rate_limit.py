"""
Rate limiting configuration using slowapi.
Uses client IP as default key; extensible to Redis in production.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["120/minute"],
    storage_uri="memory://",
)
