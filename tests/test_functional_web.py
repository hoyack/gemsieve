"""Functional tests for the GemSieve REST API."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Import ALL models so Base.metadata knows about every table
import gemsieve.web.models as _models  # noqa: F401
from gemsieve.web.models import (
    Base,
    Gem,
    Message,
    ParsedMetadata,
    SenderProfile,
    Thread,
)

# Pre-import the API module so we can patch its namespace
import gemsieve.web.api as _api_module


@pytest.fixture
def api_client():
    """FastAPI TestClient with in-memory DB and mocked task_manager."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _set_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)

    mock_tm = MagicMock()
    mock_tm.run_stage.return_value = 1  # fake run_id
    mock_tm.get_status.return_value = {"status": "completed"}

    # Save originals
    orig_session_local = _api_module.SessionLocal
    orig_task_manager = _api_module.task_manager

    # Patch the already-imported names in the api module
    _api_module.SessionLocal = TestSession
    _api_module.task_manager = mock_tm

    try:
        from fastapi import FastAPI
        from starlette.testclient import TestClient

        app = FastAPI()
        app.include_router(_api_module.router, prefix="/api")
        client = TestClient(app)
        yield client, TestSession, mock_tm
    finally:
        _api_module.SessionLocal = orig_session_local
        _api_module.task_manager = orig_task_manager


class TestGetStages:
    def test_get_stages_returns_all_seven(self, api_client):
        """GET /api/stages returns 7 stages with name, description, row_count."""
        client, _, _ = api_client
        resp = client.get("/api/stages")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 7
        stage_names = {s["name"] for s in data}
        assert stage_names == {"metadata", "content", "entities", "classify", "profile", "segment", "engage"}
        for stage in data:
            assert "name" in stage
            assert "description" in stage
            assert "row_count" in stage


class TestTopGems:
    def test_top_gems_includes_value_urgency(self, api_client):
        """GET /api/stats/gems-top/5 returns estimated_value and urgency from explanation."""
        client, SessionFactory, _ = api_client
        session = SessionFactory()
        try:
            profile = SenderProfile(
                sender_domain="test.com",
                company_name="Test",
                total_messages=1,
            )
            session.add(profile)
            session.flush()

            gem = Gem(
                gem_type="weak_marketing_lead",
                sender_domain="test.com",
                score=85,
                explanation=json.dumps({
                    "estimated_value": "high",
                    "urgency": "medium",
                    "summary": "Test gem",
                }),
                status="new",
            )
            session.add(gem)
            session.commit()
        finally:
            session.close()

        resp = client.get("/api/stats/gems-top/5")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["estimated_value"] == "high"
        assert data[0]["urgency"] == "medium"
        assert data[0]["score"] == 85

    def test_top_gems_empty_db(self, api_client):
        """GET /api/stats/gems-top/10 with empty DB returns 200 with empty list."""
        client, _, _ = api_client
        resp = client.get("/api/stats/gems-top/10")
        assert resp.status_code == 200
        assert resp.json() == []


class TestRunClassify:
    def test_run_classify_with_retrain(self, api_client):
        """POST /api/pipeline/run/classify?retrain=true passes retrain=True to task_manager."""
        client, _, mock_tm = api_client
        resp = client.post("/api/pipeline/run/classify?retrain=true")
        assert resp.status_code == 200
        mock_tm.run_stage.assert_called_once_with("classify", retrain=True)

    def test_run_classify_without_retrain(self, api_client):
        """POST /api/pipeline/run/classify without retrain param."""
        client, _, mock_tm = api_client
        resp = client.post("/api/pipeline/run/classify")
        assert resp.status_code == 200
        mock_tm.run_stage.assert_called_once_with("classify")


class TestGenerateForGem:
    def test_generate_for_gem_not_found(self, api_client):
        """POST /api/gems/999/generate returns 404 when gem doesn't exist."""
        client, _, _ = api_client
        resp = client.post("/api/gems/999/generate")
        assert resp.status_code == 404

    def test_generate_for_gem_exists(self, api_client):
        """POST /api/gems/{id}/generate triggers engagement generation."""
        client, SessionFactory, mock_tm = api_client
        session = SessionFactory()
        try:
            profile = SenderProfile(
                sender_domain="gen.com",
                company_name="GenCo",
                total_messages=1,
            )
            session.add(profile)
            session.flush()

            gem = Gem(
                gem_type="weak_marketing_lead",
                sender_domain="gen.com",
                score=60,
                explanation=json.dumps({"summary": "test"}),
                status="new",
            )
            session.add(gem)
            session.commit()
            gem_id = gem.id
        finally:
            session.close()

        resp = client.post(f"/api/gems/{gem_id}/generate")
        assert resp.status_code == 200
        body = resp.json()
        assert body["gem_id"] == gem_id
        mock_tm.run_stage.assert_called_once_with("engage", gem_id=gem_id)


class TestGetStats:
    def test_get_stats_counts_tables(self, api_client):
        """GET /api/stats returns correct counts for populated tables."""
        client, SessionFactory, _ = api_client
        session = SessionFactory()
        try:
            thread = Thread(thread_id="t1", subject="Test", message_count=1)
            session.add(thread)
            session.flush()

            msg = Message(
                message_id="m1", thread_id="t1",
                from_address="a@b.com", subject="Test",
            )
            session.add(msg)
            session.flush()

            meta = ParsedMetadata(
                message_id="m1", sender_domain="b.com",
            )
            session.add(meta)
            session.commit()
        finally:
            session.close()

        resp = client.get("/api/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["messages"] == 1
        assert data["threads"] == 1
        assert data["metadata"] == 1
        assert data["gems"] == 0
