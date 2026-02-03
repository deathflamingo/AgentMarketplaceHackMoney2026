"""Tests for agent endpoints."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register_agent_success(client: AsyncClient):
    """Test successful agent registration."""
    response = await client.post(
        "/api/agents",
        json={
            "name": "TestAgent",
            "capabilities": ["coding", "testing"],
            "description": "A test agent"
        }
    )

    assert response.status_code == 201
    data = response.json()

    assert "agent_id" in data
    assert "api_key" in data
    assert data["name"] == "TestAgent"
    assert data["api_key"].startswith("agmkt_sk_")


@pytest.mark.asyncio
async def test_register_duplicate_name_fails(client: AsyncClient):
    """Test that duplicate agent names are rejected."""
    # Create first agent
    await client.post(
        "/api/agents",
        json={"name": "UniqueAgent", "capabilities": []}
    )

    # Try to create agent with same name
    response = await client.post(
        "/api/agents",
        json={"name": "UniqueAgent", "capabilities": []}
    )

    assert response.status_code == 400
    data = response.json()
    assert data["detail"]["code"] == "DUPLICATE_AGENT_NAME"


@pytest.mark.asyncio
async def test_auth_with_valid_key(client: AsyncClient, client_agent):
    """Test authentication with valid API key."""
    agent_data, api_key = client_agent

    response = await client.get(
        "/api/agents/me",
        headers={"X-Agent-Key": api_key}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == agent_data["name"]


@pytest.mark.asyncio
async def test_auth_with_invalid_key_401(client: AsyncClient):
    """Test that invalid API key returns 401."""
    response = await client.get(
        "/api/agents/me",
        headers={"X-Agent-Key": "invalid_key"}
    )

    assert response.status_code == 401
    data = response.json()
    assert data["detail"]["code"] == "INVALID_API_KEY"


@pytest.mark.asyncio
async def test_search_agents_by_capabilities(client: AsyncClient):
    """Test searching agents by capabilities."""
    # Create agents with different capabilities
    await client.post(
        "/api/agents",
        json={"name": "CodingAgent", "capabilities": ["coding"]}
    )
    await client.post(
        "/api/agents",
        json={"name": "DesignAgent", "capabilities": ["design"]}
    )

    # Search for coding agents
    response = await client.get("/api/agents?capabilities=coding")

    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    assert any(agent["name"] == "CodingAgent" for agent in data)


@pytest.mark.asyncio
async def test_update_agent_profile(client: AsyncClient, client_agent):
    """Test updating agent profile."""
    _, api_key = client_agent

    response = await client.patch(
        "/api/agents/me",
        headers={"X-Agent-Key": api_key},
        json={
            "description": "Updated description",
            "status": "busy"
        }
    )

    assert response.status_code == 200
    data = response.json()
    assert data["description"] == "Updated description"
    assert data["status"] == "busy"


@pytest.mark.asyncio
async def test_get_agent_profile(client: AsyncClient, client_agent):
    """Test getting a specific agent's profile."""
    agent_data, _ = client_agent

    response = await client.get(f"/api/agents/{agent_data['agent_id']}")

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == agent_data["name"]


@pytest.mark.asyncio
async def test_list_agents(client: AsyncClient, client_agent, worker_agent):
    """Test listing all agents."""
    response = await client.get("/api/agents")

    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 2  # At least our two test agents
