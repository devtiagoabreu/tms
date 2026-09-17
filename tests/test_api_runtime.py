from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import tms.models  # noqa: F401  (registra as tabelas no metadata)
from tms.app.main import app
from tms.db.base import Base, get_db
from tms.ingest import pipeline

FIXTURES = Path(__file__).parent / "fixtures"


def _text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()

    pipeline.ingest_current(session, _text("current.txt"))
    pipeline.ingest_shift(session, _text("shift_2025.10.01.0.txt"), "2025.10.01.0")
    pipeline.ingest_stophistory(session, _text("stop_history_00000001.txt"))
    pipeline.ingest_operator(session, _text("operator_2025.10.01.txt"))
    pipeline.ingest_loom(session, _text("loom_00001.txt"))
    session.commit()

    def _override():
        yield session

    app.dependency_overrides[get_db] = _override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        session.close()


def test_list_machines(client):
    response = client.get("/api/machines")
    assert response.status_code == 200
    names = [m["mac_name"] for m in response.json()]
    assert "00001" in names and "00005" in names


def test_get_machine_and_404(client):
    assert client.get("/api/machines/00005").json()["mac_type"] == "LWT"
    assert client.get("/api/machines/nope").status_code == 404


def test_latest_snapshot(client):
    response = client.get("/api/machines/00001/snapshot")
    assert response.status_code == 200
    body = response.json()
    assert body["mac_name"] == "00001"
    assert body["shift_id"] == "2026.09.17.1"
    assert body["get_time"] == "2026-09-17T13:58:09"
    assert client.get("/api/machines/00005/snapshot").status_code == 404


def test_list_snapshots_filtered(client):
    response = client.get("/api/snapshots", params={"mac_name": "00001"})
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_daily_raw_filtered(client):
    response = client.get(
        "/api/daily-raw", params={"mac_name": "00001", "day_from": "2025.10.01", "day_to": "2025.10.01"}
    )
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 1
    assert rows[0]["mac_name"] == "00001"
    assert rows[0]["shift_id"] == "2025.10.01.0"


def test_agg_shift_filtered(client):
    response = client.get("/api/agg-shift", params={"shift_id": "2025.10.01.0"})
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 2
    assert {r["mac_name"] for r in rows} == {"00001", "00005"}
    assert rows[0]["stop_ct"] is not None


def test_stop_events_filtered(client):
    response = client.get(
        "/api/stop-events",
        params={"mac_name": "00001", "day": "2026.07.01", "raw_code": "0004"},
    )
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 1
    assert rows[0]["raw_code"] == "0004"
    assert rows[0]["stop_time"] > 0


def test_operator_daily_by_code(client):
    response = client.get("/api/operator-daily", params={"operator_code": "0", "day": "2025.10.01"})
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 2
    assert {r["mac_name"] for r in rows} == {"00002", "00003"}
