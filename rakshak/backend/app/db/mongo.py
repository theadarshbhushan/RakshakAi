"""
MongoDB connection and Beanie ODM initialization for multi-tenant SaaS backend.
"""
import re
from typing import Optional, Dict, Any
from beanie import init_beanie
import motor.motor_asyncio
from mongomock_motor import AsyncMongoMockClient

from app.core.config import settings
from app.core.logging import logger
from app.models import ALL_DOCUMENT_MODELS

_client: Optional[Any] = None
_db_mode: str = "disconnected"


def mask_mongo_uri(uri: str) -> str:
    """Mask credentials in MongoDB connection string for safe logging."""
    if not uri:
        return ""
    return re.sub(r"://([^:]+):([^@]+)@", "://***:***@", uri)


async def init_db() -> None:
    """
    Initialize database connection and Beanie ODM with all models and indexes.
    Uses mongomock-motor if USE_MOCK_DB is True; otherwise connects to MongoDB Atlas.
    """
    global _client, _db_mode

    if settings.USE_MOCK_DB:
        logger.info("Initializing offline Mock Database (mongomock-motor)...")
        _client = AsyncMongoMockClient()
        db = _client[settings.MONGODB_DB]
        await init_beanie(database=db, document_models=ALL_DOCUMENT_MODELS)
        _db_mode = "mock"
        logger.info("Beanie initialized successfully with offline mock database.")
        return

    # Check for MONGODB_URI
    if not settings.MONGODB_URI or not settings.MONGODB_URI.strip():
        msg = (
            "MONGODB_URI is missing from backend/.env. "
            "Please add your MongoDB Atlas connection string to backend/.env, "
            "or set USE_MOCK_DB=true in backend/.env for offline mock mode."
        )
        logger.error(msg)
        raise RuntimeError(msg)

    masked_uri = mask_mongo_uri(settings.MONGODB_URI)
    logger.info(f"Connecting to MongoDB Atlas at {masked_uri} ...")

    try:
        _client = motor.motor_asyncio.AsyncIOMotorClient(
            settings.MONGODB_URI,
            serverSelectionTimeoutMS=5000,
        )
        # Ping the cluster to verify connectivity
        await _client.admin.command("ping")
        logger.info("Successfully connected and pinged MongoDB Atlas cluster.")

        db = _client[settings.MONGODB_DB]
        await init_beanie(database=db, document_models=ALL_DOCUMENT_MODELS)
        _db_mode = "atlas"
        logger.info("Beanie ODM successfully initialized with all document models and indexes.")
    except Exception as exc:
        logger.error(
            "Failed to connect to MongoDB Atlas! Common causes:\n"
            "  1. Current IP address not added to Atlas Network Access (IP Access List / Whitelist).\n"
            "  2. Incorrect username or password in connection string.\n"
            "  3. Network firewall, VPN, or venue Wi-Fi blocking outbound port 27017.\n"
            f"Details: {exc}"
        )
        raise


async def close_db() -> None:
    """Close the database client connection."""
    global _client, _db_mode
    if _client is not None:
        _client.close()
        _client = None
        _db_mode = "disconnected"
        logger.info("Database connection closed.")


async def ping_db() -> Dict[str, Any]:
    """Health check for database connectivity."""
    global _client, _db_mode
    if _client is None:
        return {"connected": False, "mode": "disconnected", "database": settings.MONGODB_DB}

    try:
        if _db_mode == "mock":
            return {"connected": True, "mode": "mock", "database": settings.MONGODB_DB}
        await _client.admin.command("ping")
        return {"connected": True, "mode": "atlas", "database": settings.MONGODB_DB}
    except Exception as exc:
        return {"connected": False, "mode": _db_mode, "error": str(exc), "database": settings.MONGODB_DB}
