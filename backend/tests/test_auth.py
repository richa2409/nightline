"""
Basic smoke tests. Run with: pytest -v
These use an in-memory SQLite DB so CI doesn't need a live Postgres instance.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app

# The production image runs as a non-root user and keeps /app read-only at
# runtime, so the test-only SQLite file belongs in the writable temp area.
engine = create_engine("sqlite:////tmp/anon_chat_tests.db", connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(scope="module", autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


client = TestClient(app)


def test_register_and_login():
    resp = client.post("/auth/register", json={
        "email": "test@example.com",
        "password": "supersecret123",
        "interests_text": "hiking, jazz music, philosophy",
    })
    assert resp.status_code == 201
    body = resp.json()
    assert "anon_handle" in body
    assert "email" not in body  # email is never exposed to the API response

    login_resp = client.post("/auth/login", data={
        "username": "test@example.com",
        "password": "supersecret123",
    })
    assert login_resp.status_code == 200
    assert "access_token" in login_resp.json()


def test_duplicate_registration_rejected():
    client.post("/auth/register", json={
        "email": "dupe@example.com",
        "password": "supersecret123",
    })
    resp = client.post("/auth/register", json={
        "email": "dupe@example.com",
        "password": "anotherpassword",
    })
    assert resp.status_code == 400


def test_health_check():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
