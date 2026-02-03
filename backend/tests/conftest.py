"""Pytest configuration and fixtures for testing."""

import asyncio
import pytest
from typing import AsyncGenerator
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.main import app
from app.database import Base, get_db
from app.config import settings


# Test database URL (use a separate test database)
TEST_DATABASE_URL = settings.DATABASE_URL.replace("/agentmarket", "/agentmarket_test")

# Create test engine
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = async_sessionmaker(
    test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="function")
async def db() -> AsyncGenerator[AsyncSession, None]:
    """
    Create a fresh database for each test.
    """
    # Create all tables
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Create session
    async with TestSessionLocal() as session:
        yield session

    # Drop all tables after test
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def client(db: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """
    Create test client with database dependency override.
    """
    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest.fixture
async def client_agent(client: AsyncClient) -> tuple[dict, str]:
    """
    Create a client agent for testing.

    Returns:
        Tuple of (agent_data, api_key)
    """
    response = await client.post(
        "/api/agents",
        json={
            "name": "TestClient",
            "capabilities": ["orchestration"],
            "description": "Test client agent"
        }
    )
    assert response.status_code == 201
    data = response.json()
    return data, data["api_key"]


@pytest.fixture
async def worker_agent(client: AsyncClient) -> tuple[dict, str]:
    """
    Create a worker agent for testing.

    Returns:
        Tuple of (agent_data, api_key)
    """
    response = await client.post(
        "/api/agents",
        json={
            "name": "TestWorker",
            "capabilities": ["copywriting"],
            "description": "Test worker agent"
        }
    )
    assert response.status_code == 201
    data = response.json()
    return data, data["api_key"]


@pytest.fixture
async def sample_service(client: AsyncClient, worker_agent: tuple[dict, str]) -> dict:
    """
    Create a sample service for testing.

    Returns:
        Service data
    """
    _, worker_key = worker_agent

    response = await client.post(
        "/api/services",
        headers={"X-Agent-Key": worker_key},
        json={
            "name": "Test Service",
            "description": "A test service",
            "price_usd": 10.00,
            "output_type": "text",
            "required_inputs": [],
            "capabilities_required": ["copywriting"]
        }
    )
    assert response.status_code == 201
    return response.json()
