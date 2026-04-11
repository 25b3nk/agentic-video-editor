"""Tests for the /jobs API endpoints."""

from __future__ import annotations

import io
import json
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient


# ── In-memory DB + app fixture ────────────────────────────────────────────────


@pytest.fixture
async def client(tmp_path):
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app.db.session import Base, get_db
    from app.main import app

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    TestSession = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async def override_get_db():
        async with TestSession() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    with patch("app.main.start_worker", new=AsyncMock()):
        with patch("app.main.stop_worker", new=AsyncMock()):
            with patch("app.api.jobs.enqueue_job", new=AsyncMock()):
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                    yield ac

    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.fixture
async def created_workflow_id(client, minimal_workflow_yaml):
    """Helper: create a workflow and return its ID."""
    resp = await client.post("/workflows", json={"yaml_content": minimal_workflow_yaml})
    assert resp.status_code == 201
    return resp.json()["id"]


def _fake_video_file(filename: str = "test.mp4") -> tuple[str, tuple]:
    """Return a (field_name, file_tuple) for multipart upload."""
    content = b"\x00" * 200
    return ("video", (filename, io.BytesIO(content), "video/mp4"))


# ── POST /jobs ────────────────────────────────────────────────────────────────


class TestSubmitJob:
    @pytest.mark.asyncio
    async def test_submit_with_valid_params(self, client, created_workflow_id):
        params = json.dumps({"clip_duration": 3.0})
        _, file_tuple = _fake_video_file()

        response = await client.post(
            "/jobs",
            data={"workflow_id": created_workflow_id, "params": params},
            files={"video": file_tuple},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["workflow_id"] == created_workflow_id
        assert data["status"] == "pending"
        assert "id" in data

    @pytest.mark.asyncio
    async def test_submit_uses_default_params(self, client, created_workflow_id):
        _, file_tuple = _fake_video_file()

        response = await client.post(
            "/jobs",
            data={"workflow_id": created_workflow_id, "params": "{}"},
            files={"video": file_tuple},
        )
        assert response.status_code == 201
        data = response.json()
        # Default clip_duration=5.0 should be applied
        assert data["params"]["clip_duration"] == 5.0

    @pytest.mark.asyncio
    async def test_submit_nonexistent_workflow_returns_404(self, client):
        _, file_tuple = _fake_video_file()
        response = await client.post(
            "/jobs",
            data={"workflow_id": str(uuid.uuid4()), "params": "{}"},
            files={"video": file_tuple},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_submit_invalid_params_returns_422(self, client, created_workflow_id):
        # clip_duration exceeds max=30
        params = json.dumps({"clip_duration": 999.0})
        _, file_tuple = _fake_video_file()

        response = await client.post(
            "/jobs",
            data={"workflow_id": created_workflow_id, "params": params},
            files={"video": file_tuple},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_submit_invalid_json_params_returns_422(self, client, created_workflow_id):
        _, file_tuple = _fake_video_file()
        response = await client.post(
            "/jobs",
            data={"workflow_id": created_workflow_id, "params": "{invalid json}"},
            files={"video": file_tuple},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_submit_enqueues_job(self, client, created_workflow_id):
        with patch("app.api.jobs.enqueue_job", new=AsyncMock()) as mock_enqueue:
            _, file_tuple = _fake_video_file()
            response = await client.post(
                "/jobs",
                data={"workflow_id": created_workflow_id, "params": "{}"},
                files={"video": file_tuple},
            )
        assert response.status_code == 201
        mock_enqueue.assert_called_once()


# ── GET /jobs ─────────────────────────────────────────────────────────────────


class TestListJobs:
    @pytest.mark.asyncio
    async def test_empty_list(self, client):
        response = await client.get("/jobs")
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_lists_submitted_jobs(self, client, created_workflow_id):
        for _ in range(3):
            _, file_tuple = _fake_video_file()
            await client.post(
                "/jobs",
                data={"workflow_id": created_workflow_id, "params": "{}"},
                files={"video": file_tuple},
            )

        response = await client.get("/jobs")
        assert response.status_code == 200
        assert len(response.json()) == 3


# ── GET /jobs/{id} ────────────────────────────────────────────────────────────


class TestGetJob:
    @pytest.mark.asyncio
    async def test_get_existing_job(self, client, created_workflow_id):
        _, file_tuple = _fake_video_file()
        create_resp = await client.post(
            "/jobs",
            data={"workflow_id": created_workflow_id, "params": "{}"},
            files={"video": file_tuple},
        )
        job_id = create_resp.json()["id"]

        response = await client.get(f"/jobs/{job_id}")
        assert response.status_code == 200
        assert response.json()["id"] == job_id

    @pytest.mark.asyncio
    async def test_get_nonexistent_returns_404(self, client):
        response = await client.get(f"/jobs/{uuid.uuid4()}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_job_has_expected_fields(self, client, created_workflow_id):
        _, file_tuple = _fake_video_file()
        create_resp = await client.post(
            "/jobs",
            data={"workflow_id": created_workflow_id, "params": "{}"},
            files={"video": file_tuple},
        )
        job_id = create_resp.json()["id"]

        response = await client.get(f"/jobs/{job_id}")
        data = response.json()
        assert data["status"] == "pending"
        assert data["workflow_id"] == created_workflow_id
        assert data["input_video_path"] is not None
        assert data["output_video_path"] is None
        assert data["created_at"] is not None


# ── DELETE /jobs/{id} ─────────────────────────────────────────────────────────


class TestCancelJob:
    @pytest.mark.asyncio
    async def test_cancel_pending_job(self, client, created_workflow_id):
        _, file_tuple = _fake_video_file()
        create_resp = await client.post(
            "/jobs",
            data={"workflow_id": created_workflow_id, "params": "{}"},
            files={"video": file_tuple},
        )
        job_id = create_resp.json()["id"]

        response = await client.delete(f"/jobs/{job_id}")
        assert response.status_code == 204

        get_resp = await client.get(f"/jobs/{job_id}")
        assert get_resp.json()["status"] == "failed"
        assert get_resp.json()["error_message"] == "Cancelled by user"

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_returns_404(self, client):
        response = await client.delete(f"/jobs/{uuid.uuid4()}")
        assert response.status_code == 404


# ── GET /health ───────────────────────────────────────────────────────────────


class TestHealth:
    @pytest.mark.asyncio
    async def test_health_endpoint(self, client):
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
