from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import tms.models  # noqa: F401  (registra as tabelas no metadata)
from tms.app.deps.auth import SESSION_COOKIE_NAME
from tms.app.main import app
from tms.core.auth import create_session_token, hash_password
from tms.core.live import LiveStatus
from tms.db.base import Base, get_db
from tms.models.auth import User, UserRole
from tms.models.daily import DailyCollectionRun, DailyLoomData
from tms.models.masters import Machine
from tms.services import daily_collection

DAY = date(2026, 10, 27)


def _live():
    return LiveStatus(
        mac_type="JAT710",
        bits={},
        data={"rpm": 500.0, "effic_shift": 88.0, "run_time": 900.0, "stop_time": 60.0, "stop_shift": 4},
        setup={"style": "1210"},
        scnt=5,
        dcnt=13,
        vcnt=2,
    )


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    db.add_all(
        [
            Machine(mac_name="00001", mac_type="JAT", ip_addr="10.0.0.1"),
            Machine(mac_name="00002", mac_type="JAT", ip_addr="10.0.0.2"),
            User(
                email="admin@tms.local",
                username="admin",
                password_hash=hash_password("admin"),
                role=UserRole.admin,
                is_active=True,
            ),
            User(
                email="view@tms.local",
                username="view",
                password_hash=hash_password("view"),
                role=UserRole.visualizador,
                is_active=True,
            ),
        ]
    )
    db.commit()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def client(session):
    def _override():
        yield session

    app.dependency_overrides[get_db] = _override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _login(client, session, email: str):
    user = session.execute(select(User).where(User.email == email)).scalar_one()
    client.cookies.set(SESSION_COOKIE_NAME, create_session_token(user.id))


def test_daily_collect_requires_auth(client):
    response = client.post(f"/api/daily/collect?day={DAY.isoformat()}")
    assert response.status_code == 401


def test_daily_collect_rejects_non_admin(client, session):
    _login(client, session, "view@tms.local")
    response = client.post(f"/api/daily/collect?day={DAY.isoformat()}")
    assert response.status_code == 403
    assert "administradores" in response.json()["detail"]


def test_daily_collect_admin_once_per_day(client, session, monkeypatch):
    monkeypatch.setattr(daily_collection, "fetch_live", lambda ip, timeout=0: _live())
    _login(client, session, "admin@tms.local")

    first = client.post(f"/api/daily/collect?day={DAY.isoformat()}")
    assert first.status_code == 200
    body = first.json()
    assert body["status"] == "completed"
    assert body["success_count"] == 2

    second = client.post(f"/api/daily/collect?day={DAY.isoformat()}")
    assert second.status_code == 200
    assert second.json()["collection_date"] == DAY.isoformat()
    assert session.query(DailyLoomData).count() == 2

    status = client.get(f"/api/daily?day={DAY.isoformat()}")
    assert status.status_code == 200
    payload = status.json()
    assert payload["status"] == "completed"
    assert payload["summary"]["looms_collected"] == 2
    assert payload["summary"]["total_stops"] == 8


def test_daily_gaps_reports_window(client):
    response = client.get("/api/daily/gaps?days=3")
    assert response.status_code == 200
    body = response.json()
    assert len(body["days"]) == 3
    assert body["days"][-1]["status"] == "missing"
    assert body["days"][-1]["missing"] == ["00001", "00002"]


def test_daily_backfill_rejects_non_admin(client, session):
    _login(client, session, "view@tms.local")
    response = client.post("/api/daily/backfill")
    assert response.status_code == 403


def test_daily_backfill_marks_past_days_without_live_read(client, session, monkeypatch):
    calls = []
    monkeypatch.setattr(
        daily_collection,
        "fetch_live",
        lambda ip, timeout=0: calls.append(ip) or _live(),
    )
    _login(client, session, "admin@tms.local")

    start = date.today() - timedelta(days=3)
    end = date.today() - timedelta(days=2)
    response = client.post(f"/api/daily/backfill?start={start}&end={end}")

    assert response.status_code == 200
    body = response.json()
    assert [run["collection_date"] for run in body["runs"]] == [
        start.isoformat(),
        end.isoformat(),
    ]
    assert {run["status"] for run in body["runs"]} == {"no_source"}
    assert calls == []

    gaps = client.get("/api/daily/gaps?days=4")
    assert gaps.status_code == 200
    payload = gaps.json()
    assert payload["end"] == (date.today() - timedelta(days=1)).isoformat()
    by_date = {row["date"]: row for row in payload["days"]}
    assert by_date[start.isoformat()]["status"] == "no_source"
    assert by_date[start.isoformat()]["missing"] == ["00001", "00002"]


def test_daily_backfill_rejects_invalid_range(client, session):
    _login(client, session, "admin@tms.local")
    yesterday = date.today() - timedelta(days=1)
    response = client.post(
        f"/api/daily/backfill?start={yesterday}&end={yesterday - timedelta(days=2)}"
    )
    assert response.status_code == 422


def test_dashboard_mostra_card_de_producao_mensal(client, session):
    today = date.today()
    current_start = today.replace(day=1)
    previous_end = current_start - timedelta(days=1)
    previous_start = previous_end.replace(day=1)
    target = today - timedelta(days=1)

    session.add_all(
        [
            DailyCollectionRun(
                collection_date=target,
                status="completed",
                total_machines=2,
                success_count=2,
                failed_count=0,
                retry_count=0,
            ),
            DailyLoomData(
                collection_date=current_start,
                machine_id=1,
                mac_name="00001",
                source="loom_history",
                picks=12.5,
                meters=10.0,
                collected_at=datetime.utcnow(),
            ),
            DailyLoomData(
                collection_date=previous_start,
                machine_id=1,
                mac_name="00001",
                source="loom_history",
                picks=99.0,
                meters=88.0,
                collected_at=datetime.utcnow(),
            ),
        ]
    )
    session.commit()
    _login(client, session, "admin@tms.local")

    response = client.get("/")

    assert response.status_code == 200
    assert "Produção mensal" in response.text
    assert "12,5" in response.text
    assert "99,0" in response.text
