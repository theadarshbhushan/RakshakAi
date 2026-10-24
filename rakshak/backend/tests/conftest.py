"""
Pytest configuration and async client fixture.
Runs tests against isolated database 'rakshakai_test' dropped at start of session.
Tests never touch the production database 'rakshakai'.
"""
import os
import sys
from pathlib import Path
import asyncio
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
import motor.motor_asyncio

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))
sys.path.insert(0, str(backend_dir.parent))

# Force test environment variables BEFORE importing app
os.environ["ENV"] = "test"
os.environ["MONGODB_DB"] = "rakshakai_test"
os.environ["JWT_SECRET"] = "rakshakai_test_secure_jwt_secret_key_32_characters"
os.environ["RATE_LIMIT_LOGIN"] = "1000/minute"
if not os.environ.get("MONGODB_URI"):
    os.environ["MONGODB_URI"] = "mongodb://localhost:27017"
os.environ["USE_MOCK_DB"] = "false"

from app.main import app
from app.db.mongo import init_db, close_db
from scripts.seed_db import seed


@pytest.fixture(scope="session", autouse=True)
def initialize_test_database_once():
    """Drop test database at start of session and seed test data."""
    async def _setup():
        uri = os.environ.get("MONGODB_URI", "mongodb://localhost:27017")
        try:
            drop_client = motor.motor_asyncio.AsyncIOMotorClient(uri, serverSelectionTimeoutMS=2000)
            await drop_client.drop_database("rakshakai_test")
            drop_client.close()
        except Exception:
            os.environ["USE_MOCK_DB"] = "true"

        await init_db()
        await seed(close_when_done=False)
        await close_db()

    asyncio.run(_setup())
    yield


@pytest_asyncio.fixture(autouse=True)
async def setup_test_db_per_test():
    """Ensure Beanie and Motor are initialized on the current test's event loop."""
    await init_db()
    yield


@pytest_asyncio.fixture
async def client():
    """Async HTTP test client bound to FastAPI application."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

