"""
Pytest configuration and async client fixture.
Enforces USE_MOCK_DB=true and initializes mock database for all tests.
"""
import os
import sys
from pathlib import Path
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

# Set test environment variables BEFORE importing app
os.environ["USE_MOCK_DB"] = "true"
os.environ["ENV"] = "test"
os.environ["JWT_SECRET"] = "rakshakai_test_secure_jwt_secret_key_32_characters"
os.environ["RATE_LIMIT_LOGIN"] = "1000/minute"

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))
sys.path.insert(0, str(backend_dir.parent))

from app.main import app
from app.db.mongo import init_db, close_db
from scripts.seed_db import seed


@pytest_asyncio.fixture(scope="session", autouse=True)
async def initialize_test_database():
    """Initialize mock database and run seed data once for test session."""
    await init_db()
    await seed()
    yield
    await close_db()


@pytest_asyncio.fixture
async def client():
    """Async HTTP test client bound to FastAPI application."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
