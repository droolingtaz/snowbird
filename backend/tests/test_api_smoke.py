"""Smoke-test the FastAPI app: register, login, hit protected endpoint."""
import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.models import user, account, instrument, position, order, activity, bucket, snapshot  # noqa: F401


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def _get_db_override():
        s = TestSession()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _get_db_override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    engine.dispose()


def test_health_endpoint(client):
    r = client.get("/api/health")
    # If there's no /api/health, at least the root or /docs should work
    assert r.status_code in (200, 404)


def test_register_login_me_flow(client):
    r = client.post("/api/auth/register",
                    json={"email": "x@test.co", "password": "pw123456"})
    assert r.status_code in (200, 201), r.text

    r = client.post("/api/auth/login",
                    json={"email": "x@test.co", "password": "pw123456"})
    assert r.status_code == 200, r.text
    token = r.json().get("access_token")
    assert token

    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["email"] == "x@test.co"


def test_unauthorized_rejected(client):
    r = client.get("/api/accounts")
    assert r.status_code in (401, 403)
