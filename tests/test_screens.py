import copy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import tms.models  # noqa: F401  (registra as tabelas no metadata)
from tms import config_service as cfg
from tms.app.main import app
from tms.db.base import Base, get_db
from tms.ingest import pipeline
from tms.reporting import periods as reporting
from tms.reporting import screens

FIXTURES = Path(__file__).parent / "fixtures"


def _text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    pipeline.ingest_current(db, _text("current.txt"))
    pipeline.ingest_shift(db, _text("shift_2025.10.01.0.txt"), "2025.10.01.0")
    pipeline.ingest_operator(db, _text("operator_2025.10.01.txt"))
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


def _rows(session):
    return reporting.report(session, "day", key="2025.10.01")


def test_efficiency_screen(session):
    rows = _rows(session)
    screen = screens.efficiency_screen(rows, "day")
    assert screen.period_type == 1
    assert screen.header[0] == "DATE"
    assert screen.header[1:4] == ["LOOM", "STYLE", "EFFIC&PERCENT"]
    assert len(screen.rows) == len(rows) == 2

    row = rows[0]
    line = screen.rows[0]
    warp, weft = screens.warp_weft_counts(row)
    assert line[0] == 1
    assert line[1] == row.mac_name
    assert line[3] == round(row.effic, 3)
    assert line[6] == warp
    assert line[9] == weft
    if row.run_tm > 0:
        cph = warp / (row.run_tm / 60.0)
        assert line[7] == pytest.approx(round(cph, 3))
        assert line[8] == pytest.approx(round(cph * 24.0, 3))


def test_production_screen(session):
    rows = _rows(session)
    screen = screens.production_screen(rows, "day")
    assert screen.header[1:] == ["LOOM", "STYLE", "PRODUCT&PICK"]
    row = rows[0]
    assert screen.rows[0][3] == round(row.production(0), 1)
    # metragem/jarda usam o mesmo índice de unidade
    for unit in (1, 2):
        assert screens.production_screen(rows, "day", unit).rows[0][3] == round(
            row.production(unit), 1
        )


def test_stop_analysis_default_selection(session):
    rows = _rows(session)
    prefs = copy.deepcopy(cfg.SELITEM_DEFAULTS)
    screen = screens.stop_analysis_screen(rows, prefs, period="day")
    assert screen.header == [
        "DATE", "LOOM", "STYLE", "WARP",
        "WF1&COLOR1", "WF1&COLOR2", "WEFT_OTHER", "LENO_L", "LENO_R", "UNSELECT",
    ]

    row = rows[0]
    line = screen.rows[0]
    unsel = line[-1]
    expected_unsel = sum(row.stop_ct[i] for i in (2, 11, 6, 7, 8, 9, 10))
    expected_unsel += sum(row.wf1_ct[2:6]) + sum(row.wf2_ct) + sum(row.lh_ct)
    assert unsel == expected_unsel
    weft_other = line[screen.header.index("WEFT_OTHER")]
    assert weft_other == sum(row.wf1_ct[2:6]) + sum(row.wf2_ct) + sum(row.lh_ct)


def test_stop_analysis_time_output(session):
    rows = _rows(session)
    prefs = copy.deepcopy(cfg.SELITEM_DEFAULTS)
    count = screens.stop_analysis_screen(rows, prefs, period="day", time=False)
    time = screens.stop_analysis_screen(rows, prefs, period="day", time=True)
    assert time.header == count.header
    row = rows[0]
    expected = sum(row.stop_tm[i] for i in (2, 11, 6, 7, 8, 9, 10))
    expected += sum(row.wf1_tm[2:6]) + sum(row.wf2_tm) + sum(row.lh_tm)
    assert time.rows[0][-1] == pytest.approx(expected)


def test_stop_analysis_warp_top_toggle(session):
    rows = _rows(session)
    prefs = copy.deepcopy(cfg.SELITEM_DEFAULTS)
    prefs["item"][0] = 1
    screen = screens.stop_analysis_screen(rows, prefs, period="day", beam_type=2)
    assert "WARP_TOP" in screen.header


def test_efficiency_endpoint(client):
    response = client.get("/api/screens/efficiency", params={"key": "2025.10.01"})
    assert response.status_code == 200
    body = response.json()
    assert body["period_type"] == 1
    assert body["header"][0] == "DATE"
    assert len(body["rows"]) == 2

    csv_response = client.get("/api/screens/efficiency.csv", params={"key": "2025.10.01"})
    assert csv_response.status_code == 200
    assert csv_response.headers["content-type"].startswith("text/csv")
    assert csv_response.text.splitlines()[0].startswith("DATE,LOOM,STYLE")


def test_production_endpoint(client):
    response = client.get(
        "/api/screens/production", params={"key": "2025.10.01", "unit": 2}
    )
    assert response.status_code == 200
    assert response.json()["header"][3] == "PRODUCT&YARD"


def test_stop_analysis_endpoint(client):
    response = client.get("/api/screens/stop-analysis", params={"key": "2025.10.01"})
    assert response.status_code == 200
    body = response.json()
    assert body["header"][-1] == "UNSELECT"
    assert len(body["count_rows"]) == len(body["time_rows"]) == 2

    csv_response = client.get(
        "/api/screens/stop-analysis.csv", params={"key": "2025.10.01", "value": "time"}
    )
    assert csv_response.status_code == 200
    assert csv_response.text.splitlines()[0].startswith("DATE,LOOM,STYLE")


def test_screens_invalid_period(client):
    assert client.get("/api/screens/efficiency", params={"period": "hour"}).status_code == 404
