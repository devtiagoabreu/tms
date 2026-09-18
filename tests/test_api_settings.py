import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import tms.models  # noqa: F401  (registra as tabelas no metadata)
from tms.app.main import app
from tms.db.base import Base, get_db


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()

    def _override():
        yield session

    app.dependency_overrides[get_db] = _override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        session.close()


def test_ip_ranges_endpoint(client):
    put = client.put(
        "/api/settings/ip-ranges",
        json={"text": "172 17 1 1 16\n172 17 1 17 20\n"},
    )
    assert put.status_code == 200
    assert put.json()["ranges"] == [[172, 17, 1, 1, 20]]
    assert len(put.json()["ips"]) == 20

    got = client.get("/api/settings/ip-ranges")
    assert got.json()["text"] == "172 17 1 1 20\n"
    assert got.json()["ips"][0] == "172.17.1.1"
    assert got.json()["ips"][-1] == "172.17.1.20"


def test_styles_endpoint(client):
    response = client.put("/api/settings/styles", json={"text": "2312\t70\t100\n"})
    assert response.status_code == 200
    assert response.json()["styles"][0]["name"] == "2312"
    got = client.get("/api/settings/styles")
    assert got.json()["styles"][0]["doff_len"] == 100


def test_shift_endpoint(client):
    text = "shift_schedule_is_week 0\nshift_schedule_simple 3 05:00 14:00 23:35\n"
    response = client.put("/api/settings/shift", json={"text": text})
    assert response.status_code == 200
    assert response.json()["simple"][0] == 3
    assert client.get("/api/settings/shift").json()["simple"][1] == "05:00"


def test_report_prefs_endpoint(client):
    response = client.put(
        "/api/settings/report-prefs", json={"prefs": {"effic": 85, "period": "date"}}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["effic"] == 85 and body["period"] == "date"
    assert body["item2"] == [0, 0, 1, 1, 1, 1, 1]
    assert client.get("/api/settings/report-prefs").json()["effic"] == 85


def test_value_endpoint(client):
    assert client.get("/api/settings/value/language").json() == {
        "key": "language",
        "value": None,
    }
    client.put("/api/settings/value/language", json={"value": "pt"})
    assert client.get("/api/settings/value/language").json()["value"] == "pt"
    assert client.get("/api/settings").json()["language"] == "pt"
    client.put("/api/settings/value/language", json={"value": None})
    assert client.get("/api/settings/value/language").json()["value"] is None
