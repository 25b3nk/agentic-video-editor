"""Tests for the /workflows API endpoints."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient


# ── In-memory DB fixture ──────────────────────────────────────────────────────


@pytest.fixture
async def client(tmp_path):
    """AsyncClient backed by the FastAPI app with an in-memory SQLite DB."""
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

    # Prevent the worker from running in tests
    with patch("app.main.start_worker", new=AsyncMock()):
        with patch("app.main.stop_worker", new=AsyncMock()):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                yield ac

    app.dependency_overrides.clear()
    await engine.dispose()


# ── POST /workflows ───────────────────────────────────────────────────────────


class TestCreateWorkflow:
    @pytest.mark.asyncio
    async def test_create_minimal_workflow(self, client, minimal_workflow_yaml):
        response = await client.post("/workflows", json={"yaml_content": minimal_workflow_yaml})
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Test Workflow"
        assert data["author"] == "test"
        assert "id" in data
        assert "yaml_content" in data

    @pytest.mark.asyncio
    async def test_create_poster_workflow(self, client, poster_workflow_yaml):
        response = await client.post("/workflows", json={"yaml_content": poster_workflow_yaml})
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Action Poster Reveal"

    @pytest.mark.asyncio
    async def test_create_invalid_yaml_returns_422(self, client):
        response = await client.post("/workflows", json={"yaml_content": "- bad [yaml"})
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_missing_metadata_returns_422(self, client):
        yaml = "steps:\n  - id: s\n    type: noop\n"
        response = await client.post("/workflows", json={"yaml_content": yaml})
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_unknown_step_type_returns_422(self, client):
        yaml = """\
version: "1.0"
metadata:
  name: T
  description: d
  author: a
steps:
  - id: bad
    type: does_not_exist
"""
        response = await client.post("/workflows", json={"yaml_content": yaml})
        assert response.status_code == 422


# ── GET /workflows ────────────────────────────────────────────────────────────


class TestListWorkflows:
    @pytest.mark.asyncio
    async def test_empty_list(self, client):
        response = await client.get("/workflows")
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_lists_created_workflows(self, client, minimal_workflow_yaml, poster_workflow_yaml):
        await client.post("/workflows", json={"yaml_content": minimal_workflow_yaml})
        await client.post("/workflows", json={"yaml_content": poster_workflow_yaml})

        response = await client.get("/workflows")
        assert response.status_code == 200
        assert len(response.json()) == 2

    @pytest.mark.asyncio
    async def test_list_returns_summary_fields(self, client, minimal_workflow_yaml):
        await client.post("/workflows", json={"yaml_content": minimal_workflow_yaml})
        response = await client.get("/workflows")
        item = response.json()[0]
        assert "id" in item
        assert "name" in item
        assert "created_at" in item
        # yaml_content not included in list view
        assert "yaml_content" not in item


# ── GET /workflows/{id} ───────────────────────────────────────────────────────


class TestGetWorkflow:
    @pytest.mark.asyncio
    async def test_get_existing(self, client, minimal_workflow_yaml):
        create_resp = await client.post("/workflows", json={"yaml_content": minimal_workflow_yaml})
        wf_id = create_resp.json()["id"]

        response = await client.get(f"/workflows/{wf_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == wf_id
        assert data["yaml_content"] == minimal_workflow_yaml

    @pytest.mark.asyncio
    async def test_get_nonexistent_returns_404(self, client):
        response = await client.get(f"/workflows/{uuid.uuid4()}")
        assert response.status_code == 404


# ── DELETE /workflows/{id} ────────────────────────────────────────────────────


class TestDeleteWorkflow:
    @pytest.mark.asyncio
    async def test_delete_existing(self, client, minimal_workflow_yaml):
        create_resp = await client.post("/workflows", json={"yaml_content": minimal_workflow_yaml})
        wf_id = create_resp.json()["id"]

        response = await client.delete(f"/workflows/{wf_id}")
        assert response.status_code == 204

        # Confirm gone
        get_resp = await client.get(f"/workflows/{wf_id}")
        assert get_resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_nonexistent_returns_404(self, client):
        response = await client.delete(f"/workflows/{uuid.uuid4()}")
        assert response.status_code == 404
