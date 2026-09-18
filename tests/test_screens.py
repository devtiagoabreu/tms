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


def test_report_shift_period(session):
    """period=shift agrupa por shift_id (chave = 2025.10.01.0)."""
    rows = reporting.report(session, "shift", key="2025.10.01.0")
    assert len(rows) == 2
    assert rows[0].key == "2025.10.01.0"


def test_report_shift_invalid_operator_mode(session):
    """mode=operator + period=shift deve levantar ValueError."""
    with pytest.raises(ValueError, match="turno"):
        reporting.report(session, "shift", mode="operator")


def _operator_text(ope_nums=("1", "2"), names=("Ope1", "Ope2")):
    """`operator_2025.10.01.txt` com ope_num/ope_name distintos por tear."""
    import re

    out = []
    for i, line in enumerate([ln for ln in _text("operator_2025.10.01.txt").splitlines() if ln.strip()]):
        line = line.replace("ope_num 0", f"ope_num {ope_nums[i]}")
        line = re.sub(r"ope_name [^,]+", f"ope_name {names[i]}", line)
        out.append(line)
    return "\n".join(out)


@pytest.fixture
def op_session():
    """Sessão com `operator_daily` de 2 operadores distintos (sem shift/operador default)."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    pipeline.ingest_current(db, _text("current.txt"))
    pipeline.ingest_operator(db, _operator_text())
    db.commit()
    try:
        yield db
    finally:
        db.close()


def test_report_operator_mode(op_session):
    """mode=operator agrega operator_daily por nome do operador."""
    rows = reporting.report(op_session, "day", key="2025.10.01", mode="operator")
    assert len(rows) == 2
    operators = {r.operator for r in rows}
    assert operators == {"Ope1", "Ope2"}
    for r in rows:
        assert r.operator is not None


def test_efficiency_operator_mode(op_session):
    """efficiency_screen com mode=operator tem header OPERATOR (sem LOOM/STYLE)."""
    rows = reporting.report(op_session, "day", key="2025.10.01", mode="operator")
    screen = screens.efficiency_screen(rows, "day", mode="operator")
    assert screen.header[1] == "OPERATOR"
    assert "LOOM" not in screen.header
    assert "STYLE" not in screen.header
    assert len(screen.rows) == 2
    operators_in_data = {line[1] for line in screen.rows}
    assert operators_in_data == {"Ope1", "Ope2"}


def test_production_operator_mode(op_session):
    """production_screen com mode=operator."""
    rows = reporting.report(op_session, "day", key="2025.10.01", mode="operator")
    screen = screens.production_screen(rows, "day", mode="operator")
    assert screen.header[1] == "OPERATOR"
    assert "LOOM" not in screen.header


def test_stop_analysis_operator_mode(op_session):
    """stop_analysis_screen com mode=operator."""
    rows = reporting.report(op_session, "day", key="2025.10.01", mode="operator")
    prefs = copy.deepcopy(cfg.SELITEM_DEFAULTS)
    screen = screens.stop_analysis_screen(rows, prefs, period="day", mode="operator")
    assert screen.header[1] == "OPERATOR"
    assert "LOOM" not in screen.header
    assert "STYLE" not in screen.header


def test_efficiency_shift_endpoint(client):
    """GET /api/screens/efficiency?period=shift"""
    response = client.get("/api/screens/efficiency", params={"period": "shift"})
    assert response.status_code == 200
    body = response.json()
    assert body["period_type"] == 0
    assert body["header"][0] == "SHIFT"


def test_efficiency_operator_endpoint(client):
    """GET /api/screens/efficiency?mode=operator"""
    response = client.get("/api/screens/efficiency", params={"mode": "operator"})
    assert response.status_code == 200
    body = response.json()
    assert body["header"][1] == "OPERATOR"


def test_production_shift_endpoint(client):
    response = client.get("/api/screens/production", params={"period": "shift"})
    assert response.status_code == 200
    assert response.json()["header"][0] == "SHIFT"


def test_stop_analysis_shift_endpoint(client):
    response = client.get("/api/screens/stop-analysis", params={"period": "shift"})
    assert response.status_code == 200
    assert response.json()["period_type"] == 0


def test_stop_analysis_operator_endpoint(client):
    response = client.get("/api/screens/stop-analysis", params={"mode": "operator"})
    assert response.status_code == 200
    body = response.json()
    assert body["header"][1] == "OPERATOR"


def test_screens_operator_shift_conflict(client):
    """mode=operator + period=shift → 400."""
    response = client.get(
        "/api/screens/efficiency",
        params={"period": "shift", "mode": "operator"},
    )
    assert response.status_code == 400


def test_machine_aris(session):
    """Fixture tem JAT (00001/00002) e LWT (00005)."""
    assert reporting.machine_aris(session) == (True, True)


# -------------------------------------------------------------- shiftreport --

def test_shiftreport_screen(session):
    rows = reporting.report(session, "day", key="2025.10.01")
    prefs = copy.deepcopy(cfg.SELITEM_DEFAULTS)
    screen = screens.shiftreport_screen(rows, prefs, period="day")
    assert screen.header[0] == "DATE"
    assert all(len(line) == len(screen.header) for line in screen.rows)
    headers = screen.header
    assert headers[1:4] == ["LOOM", "MAC_TYPE", "STYLE"]  # JAT + LWT presentes
    assert "WARP&COUNT" in headers and "WARP&RATE_PP" in headers
    assert "TOTAL&COUNT" in headers and "UNSELECT&COUNT" in headers

    row = rows[0]
    line = screen.rows[0]
    assert line[headers.index("WARP&COUNT")] == row.stop_ct[1]
    assert line[headers.index("WEFT&COUNT")] == row.stop_ct[5]
    assert line[headers.index("TOTAL&COUNT")] == row.total_ct(1)
    assert line[headers.index("TOTAL&MINUTE")] == round(
        sum(row.stop_tm[:12]) - row.stop_tm[0], 3
    )
    assert line[headers.index("WARP&MINUTE")] == round(row.stop_tm[1], 3)
    assert line[headers.index("PRODUCT&PICK")] == round(row.seisan[0], 3)
    hours = row.run_tm / 60.0
    assert line[headers.index("WARP&RATE_PH")] == (
        round(row.stop_ct[1] / hours, 3) if hours > 0 else 0.0
    )
    assert line[headers.index("WF1&COLOR1&COUNT")] == row.wf1_ct[0]
    assert line[headers.index("LENO_L&COUNT")] == row.stop_ct[3]


def test_shiftreport_sel_style_orders_ident(session):
    rows = reporting.report(session, "day", key="2025.10.01")
    prefs = copy.deepcopy(cfg.SELITEM_DEFAULTS)
    screen = screens.shiftreport_screen(rows, prefs, period="day", sel="style")
    assert screen.header[1:4] == ["STYLE", "LOOM", "MAC_TYPE"]


def test_shiftreport_single_machine_type_no_mac_type(session):
    rows = reporting.report(session, "day", key="2025.10.01")
    prefs = copy.deepcopy(cfg.SELITEM_DEFAULTS)
    screen = screens.shiftreport_screen(rows, prefs, period="day", jat_ari=True, lwt_ari=False)
    assert screen.header[1:3] == ["LOOM", "STYLE"]
    assert "MAC_TYPE" not in screen.header


def test_shiftreport_operator_mode(op_session):
    rows = reporting.report(op_session, "day", key="2025.10.01", mode="operator")
    prefs = copy.deepcopy(cfg.SELITEM_DEFAULTS)
    screen = screens.shiftreport_screen(rows, prefs, period="day", mode="operator")
    assert screen.header[1] == "OPERATOR"
    assert "LOOM" not in screen.header
    assert "MAC_TYPE" not in screen.header
    assert {line[1] for line in screen.rows} == {"Ope1", "Ope2"}


def test_shiftreport_warp_top_with_beam_type_2(session):
    """beam_type=2 seleciona WARP_TOP (sem UNSELECT incluir warp top único)."""
    rows = reporting.report(session, "day", key="2025.10.01")
    prefs = copy.deepcopy(cfg.SELITEM_DEFAULTS)
    prefs["item"][0] = 1
    screen = screens.shiftreport_screen(rows, prefs, period="day", beam_type=2)
    assert "WARP_TOP&COUNT" in screen.header


# -------------------------------------------------------------- stylereport --

def test_stylereport_screen(session):
    rows = reporting.report(session, "day", key="2025.10.01", mode="style")
    assert len(rows) == 2
    prefs = copy.deepcopy(cfg.SELITEM_DEFAULTS)
    screen = screens.stylereport_screen(rows, prefs, period="day")
    assert screen.header[0] == "DATE"
    assert screen.header[1:5] == ["LOOM", "SORTKEY", "STYLE", "LOOM_COUNT"]
    assert all(len(line) == len(screen.header) for line in screen.rows)

    row = rows[0]
    line = screen.rows[0]
    assert line[1] == "" and line[2] == ""  # LOOM/SORTKEY vazios no agregado
    assert line[3] == row.style
    assert line[4] == row.loom_count == 1  # 1 tear por estilo no fixture


def test_shiftreport_endpoint(client):
    response = client.get("/api/screens/shiftreport", params={"period": "day", "key": "2025.10.01"})
    assert response.status_code == 200
    body = response.json()
    assert body["period_type"] == 1
    assert body["header"][1:4] == ["LOOM", "MAC_TYPE", "STYLE"]
    assert len(body["rows"]) == 2

    csv_response = client.get(
        "/api/screens/shiftreport.csv", params={"period": "day", "key": "2025.10.01"}
    )
    assert csv_response.status_code == 200
    assert csv_response.text.splitlines()[0].startswith("DATE,LOOM,MAC_TYPE,STYLE")


def test_shiftreport_shift_period_endpoint(client):
    response = client.get("/api/screens/shiftreport", params={"period": "shift", "key": "2025.10.01.0"})
    assert response.status_code == 200
    assert response.json()["header"][0] == "SHIFT"


def test_shiftreport_default_period_from_prefs(client):
    """Sem `period`, usa o selitem (default "shift")."""
    response = client.get("/api/screens/shiftreport")
    assert response.status_code == 200
    assert response.json()["header"][0] == "SHIFT"


def test_shiftreport_operator_shift_conflict(client):
    assert client.get(
        "/api/screens/shiftreport", params={"period": "shift", "mode": "operator"}
    ).status_code == 400


def test_stylereport_endpoint(client):
    response = client.get("/api/screens/stylereport", params={"period": "day", "key": "2025.10.01"})
    assert response.status_code == 200
    body = response.json()
    assert body["header"][1:5] == ["LOOM", "SORTKEY", "STYLE", "LOOM_COUNT"]
    assert len(body["rows"]) == 2

    csv_response = client.get(
        "/api/screens/stylereport.csv", params={"period": "day", "key": "2025.10.01"}
    )
    assert csv_response.status_code == 200
    assert csv_response.text.splitlines()[0].startswith("DATE,LOOM,SORTKEY,STYLE,LOOM_COUNT")
