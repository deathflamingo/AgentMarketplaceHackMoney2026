"""Tests for job workflow endpoints."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_job_direct_purchase(
    client: AsyncClient,
    client_agent,
    worker_agent,
    sample_service
):
    """Test creating a job (direct purchase of service)."""
    _, client_key = client_agent

    response = await client.post(
        "/api/jobs",
        headers={"X-Agent-Key": client_key},
        json={
            "service_id": sample_service["id"],
            "title": "Test Job",
            "input_data": {"test": "data"}
        }
    )

    assert response.status_code == 201
    data = response.json()

    assert data["status"] == "pending"
    assert data["service_id"] == sample_service["id"]
    assert float(data["price_usd"]) == 10.00  # Price locked from service


@pytest.mark.asyncio
async def test_start_job_as_worker(
    client: AsyncClient,
    client_agent,
    worker_agent,
    sample_service
):
    """Test worker starting a job."""
    _, client_key = client_agent
    _, worker_key = worker_agent

    # Create job
    job_response = await client.post(
        "/api/jobs",
        headers={"X-Agent-Key": client_key},
        json={"service_id": sample_service["id"], "input_data": {}}
    )
    job_id = job_response.json()["id"]

    # Worker starts job
    response = await client.post(
        f"/api/jobs/{job_id}/start",
        headers={"X-Agent-Key": worker_key},
        json={}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "in_progress"


@pytest.mark.asyncio
async def test_deliver_work(
    client: AsyncClient,
    client_agent,
    worker_agent,
    sample_service
):
    """Test worker delivering work."""
    _, client_key = client_agent
    _, worker_key = worker_agent

    # Create and start job
    job_response = await client.post(
        "/api/jobs",
        headers={"X-Agent-Key": client_key},
        json={"service_id": sample_service["id"], "input_data": {}}
    )
    job_id = job_response.json()["id"]

    await client.post(
        f"/api/jobs/{job_id}/start",
        headers={"X-Agent-Key": worker_key},
        json={}
    )

    # Deliver work
    response = await client.post(
        f"/api/jobs/{job_id}/deliver",
        headers={"X-Agent-Key": worker_key},
        json={
            "artifact_type": "text",
            "content": "Here is the completed work",
            "metadata": {"word_count": 5}
        }
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "delivered"


@pytest.mark.asyncio
async def test_complete_with_rating(
    client: AsyncClient,
    client_agent,
    worker_agent,
    sample_service
):
    """Test client completing job with rating."""
    _, client_key = client_agent
    worker_data, worker_key = worker_agent

    # Create, start, and deliver job
    job_response = await client.post(
        "/api/jobs",
        headers={"X-Agent-Key": client_key},
        json={"service_id": sample_service["id"], "input_data": {}}
    )
    job_id = job_response.json()["id"]

    await client.post(
        f"/api/jobs/{job_id}/start",
        headers={"X-Agent-Key": worker_key},
        json={}
    )

    await client.post(
        f"/api/jobs/{job_id}/deliver",
        headers={"X-Agent-Key": worker_key},
        json={"artifact_type": "text", "content": "Work done"}
    )

    # Complete with rating
    response = await client.post(
        f"/api/jobs/{job_id}/complete",
        headers={"X-Agent-Key": client_key},
        json={
            "rating": 5,
            "review": "Excellent work!"
        }
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["rating"] == 5

    # Verify reputation updated
    agent_response = await client.get(f"/api/agents/{worker_data['agent_id']}")
    agent_data = agent_response.json()
    assert float(agent_data["reputation_score"]) == 5.0


@pytest.mark.asyncio
async def test_invalid_status_transition_fails(
    client: AsyncClient,
    client_agent,
    worker_agent,
    sample_service
):
    """Test that invalid state transitions are rejected."""
    _, client_key = client_agent
    _, worker_key = worker_agent

    # Create job
    job_response = await client.post(
        "/api/jobs",
        headers={"X-Agent-Key": client_key},
        json={"service_id": sample_service["id"], "input_data": {}}
    )
    job_id = job_response.json()["id"]

    # Try to deliver without starting (invalid transition)
    response = await client.post(
        f"/api/jobs/{job_id}/deliver",
        headers={"X-Agent-Key": worker_key},
        json={"artifact_type": "text", "content": "Work"}
    )

    assert response.status_code == 400
    assert "cannot deliver" in response.json()["detail"]["message"].lower()


@pytest.mark.asyncio
async def test_cancel_pending_job(
    client: AsyncClient,
    client_agent,
    sample_service
):
    """Test cancelling a pending job."""
    _, client_key = client_agent

    # Create job
    job_response = await client.post(
        "/api/jobs",
        headers={"X-Agent-Key": client_key},
        json={"service_id": sample_service["id"], "input_data": {}}
    )
    job_id = job_response.json()["id"]

    # Cancel job
    response = await client.post(
        f"/api/jobs/{job_id}/cancel",
        headers={"X-Agent-Key": client_key}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "cancelled"


@pytest.mark.asyncio
async def test_cannot_cancel_in_progress_job(
    client: AsyncClient,
    client_agent,
    worker_agent,
    sample_service
):
    """Test that in-progress jobs cannot be cancelled."""
    _, client_key = client_agent
    _, worker_key = worker_agent

    # Create and start job
    job_response = await client.post(
        "/api/jobs",
        headers={"X-Agent-Key": client_key},
        json={"service_id": sample_service["id"], "input_data": {}}
    )
    job_id = job_response.json()["id"]

    await client.post(
        f"/api/jobs/{job_id}/start",
        headers={"X-Agent-Key": worker_key},
        json={}
    )

    # Try to cancel (should fail)
    response = await client.post(
        f"/api/jobs/{job_id}/cancel",
        headers={"X-Agent-Key": client_key}
    )

    assert response.status_code == 400
    assert "cannot cancel" in response.json()["detail"]["message"].lower()


@pytest.mark.asyncio
async def test_request_revision(
    client: AsyncClient,
    client_agent,
    worker_agent,
    sample_service
):
    """Test requesting revision for delivered work."""
    _, client_key = client_agent
    _, worker_key = worker_agent

    # Create, start, and deliver job
    job_response = await client.post(
        "/api/jobs",
        headers={"X-Agent-Key": client_key},
        json={"service_id": sample_service["id"], "input_data": {}}
    )
    job_id = job_response.json()["id"]

    await client.post(
        f"/api/jobs/{job_id}/start",
        headers={"X-Agent-Key": worker_key},
        json={}
    )

    await client.post(
        f"/api/jobs/{job_id}/deliver",
        headers={"X-Agent-Key": worker_key},
        json={"artifact_type": "text", "content": "Initial work"}
    )

    # Request revision
    response = await client.post(
        f"/api/jobs/{job_id}/request-revision",
        headers={"X-Agent-Key": client_key},
        json={"feedback": "Please add more details"}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "revision_requested"
