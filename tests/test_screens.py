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
from tms.reporting import history
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
    pipeline.ingest_stophistory(db, _text("stop_history_00000001.txt"))
    pipeline.ingest_stophistory(db, _text("stop_history_open_00000002.txt"))
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


# ------------------------------------------------------------- statushistory --

def test_statushistory_screen_equals_efficiency(session):
    """statushistory = colunas do efficiency (WARP = stop[0..4]+stop[11])."""
    rows = _rows(session)
    screen = screens.statushistory_screen(rows, "day")
    ref = screens.efficiency_screen(rows, "day")
    assert screen.header == ref.header == ["DATE", *screens.EFFICIENCY_COLUMNS]
    assert screen.rows == ref.rows


def test_statushistory_endpoint_filters_by_loom(client):
    response = client.get(
        "/api/screens/statushistory",
        params={"period": "day", "key": "2025.10.01", "sel_mode": "loom", "loom": "00001"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["period_type"] == 1
    assert body["header"][0] == "DATE"
    assert body["header"][1:] == list(screens.EFFICIENCY_COLUMNS)
    assert len(body["rows"]) == 1
    assert body["rows"][0][1] == "00001"

    csv_response = client.get(
        "/api/screens/statushistory.csv",
        params={"period": "day", "key": "2025.10.01", "sel_mode": "style", "style": "1420"},
    )
    assert csv_response.status_code == 200
    assert csv_response.text.splitlines()[0].startswith("DATE,LOOM,STYLE")


def test_statushistory_endpoint_style_filter(client):
    response = client.get(
        "/api/screens/statushistory",
        params={"period": "day", "key": "2025.10.01", "sel_mode": "style", "style": "1420"},
    )
    body = response.json()
    assert len(body["rows"]) == 1
    assert body["rows"][0][2] == "1420"


# ---------------------------------------------------------------- svsreport --

def test_svsreport_screen(session):
    rows = _rows(session)
    prefs = copy.deepcopy(cfg.SELITEM_DEFAULTS)  # color = [1,1,0,0,0,0], beam_type=1
    screen = screens.svsreport_screen(rows, prefs, period="day")
    assert screen.header[0:3] == ["STYLE", "LOOM", "DATE"]
    assert screen.header[3:9] == [
        "RUN&MINUTE", "STOP&MINUTE", "PRODUCT&PICK", "EFFIC&PERCENT", "RPM", "WARP",
    ]
    assert "WARP_TOP" not in screen.header
    assert "WARP_BOTTOM" in screen.header
    assert screen.header[-4:] == ["WF1&COLOR1", "WF1&COLOR2", "WF2&COLOR1", "WF2&COLOR2"]

    row = rows[0]  # 00001 JAT: stop_ct=[0,2,0,0,0,10,...], wf1=[1,9,0,0,0,0]
    line = screen.rows[0]
    assert line[0] == "2312" and line[1] == "00001" and line[2] == 1
    assert line[5] == 216000.0
    assert line[8] == 2          # WARP = stop[0]+stop[1]
    assert line[9] == 10         # WF1 = sum(wf1_ct)
    assert line[10] == 0         # WF2
    assert line[11] == 0         # OTHER = stop[2..4]+stop[11]+lh
    assert line[12] == 12        # TOTAL
    assert line[13] == 2         # WARP_BOTTOM = stop[1]
    assert line[14] == 1         # WF1&COLOR1
    assert line[15] == 9         # WF1&COLOR2
    assert line[16] == 0 and line[17] == 0  # WF2&COLOR1/2


def test_svsreport_screen_beam_type_2(session):
    rows = _rows(session)
    prefs = copy.deepcopy(cfg.SELITEM_DEFAULTS)
    screen = screens.svsreport_screen(rows, prefs, period="day", beam_type=2)
    assert "WARP_TOP" in screen.header
    idx = screen.header.index("WARP_TOP")
    assert screen.rows[0][idx] == 0  # stop_ct[0]


def test_svsreport_endpoint(client):
    response = client.get(
        "/api/screens/svsreport",
        params={"period": "day", "key": "2025.10.01", "beam_type": 2},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["header"][0] == "STYLE"
    assert "WARP_TOP" in body["header"]
    assert len(body["rows"]) == 2

    csv_response = client.get("/api/screens/svsreport.csv", params={"period": "day", "key": "2025.10.01"})
    assert csv_response.status_code == 200
    assert csv_response.text.splitlines()[0].startswith("STYLE,LOOM,DATE")


# -------------------------------------------------------------- stophistory --

def test_load_stop_events(session):
    rows = history.load_stop_events(session, day_from="2026.07.01", day_to="2026.09.17")
    assert len(rows) == 6
    assert rows[0].mac_name == "00001"
    assert rows[0].day == "2026.07.01"
    assert rows[0].stop_time == 6 * 3600 + 36 * 60 + 9
    assert rows[0].run_time == 0
    assert rows[0].raw_code == "2153"
    # 4 do 00001 + 2 do 00002 (ordem: dia, tear)
    assert rows[4].mac_name == "00002"


def test_load_stop_events_filters(session):
    rows = history.load_stop_events(session, mac_name="00002")
    assert len(rows) == 2
    assert [r.day for r in rows] == ["2026.09.17", "2026.09.17"]
    assert rows[1].raw_code == "0004"


def test_stophistory_screen(session):
    rows = history.load_stop_events(session, mac_name="00001")
    screen = screens.stophistory_screen(rows)
    assert screen.header == [
        "ORDER", "DATE", "LOOM", "STOP_TIME_POINT", "RUN_TIME_POINT",
        "STOP_CODE", "STOP_CAUSE",
    ]
    line = screen.rows[0]
    assert line == [1, "2026.07.01", "00001", "06:36:09", "00:00:00", "2153", "DECLARE(WARP OUT)"]
    assert screen.rows[1][5] == "0027"
    assert screen.rows[1][6] == "[STOP] SWITCH PRESSED"
    assert screen.rows[3][5] == "0004"
    assert screen.rows[3][6] == "WEFT STOP BY WF1 (COLOR 1)"


def test_stophistory_endpoint(client):
    response = client.get(
        "/api/screens/stophistory", params={"day_from": "2026.07.01", "mac_name": "00001"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["period_type"] == 0
    assert len(body["rows"]) == 4
    assert body["rows"][0][-1] == "DECLARE(WARP OUT)"

    csv_response = client.get("/api/screens/stophistory.csv")
    assert csv_response.status_code == 200
    assert csv_response.text.splitlines()[0].startswith("ORDER,DATE,LOOM")


# ---------------------------------------------------------------- showstyle --

def test_load_showstyle_records_shift(session):
    rows = history.load_showstyle_records(session, source="shift")
    assert [(r.key, r.mac_name, r.style) for r in rows] == [
        ("2025.10.01.0", "00001", "2312"),
        ("2025.10.01.0", "00005", "1420"),
    ]


def test_load_showstyle_records_operator(op_session):
    rows = history.load_showstyle_records(op_session, source="operator")
    assert rows[0].key == "2025.10.01"
    assert {(r.mac_name, r.operator_name) for r in rows} == {
        ("00002", "Ope1"), ("00003", "Ope2"),
    }
    assert all(r.style == "2312" for r in rows)


def test_showstyle_screen_shift_loom(session):
    rows = history.load_showstyle_records(session, source="shift")
    screen = screens.showstyle_screen(rows, data="shift", sel_mode="loom")
    assert screen.header == ["SHIFT", "00001", "00005"]
    assert screen.rows == [["2025.10.01.0", "2312", "1420"]]


def test_showstyle_screen_shift_style(session):
    rows = history.load_showstyle_records(session, source="shift")
    screen = screens.showstyle_screen(rows, data="shift", sel_mode="style")
    assert screen.header == ["SHIFT", "2312", "1420"]
    assert screen.rows == [["2025.10.01.0", "00001", "00005"]]


def test_showstyle_screen_operator(op_session):
    rows = history.load_showstyle_records(op_session, source="operator")
    screen = screens.showstyle_screen(
        rows, data="operator", sel_mode="loom", loom=["00002"]
    )
    assert screen.header == ["DATE", "00002+&+Ope1"]
    assert screen.rows == [["2025.10.01", "2312"]]


def test_showstyle_screen_operator_by_style(op_session):
    rows = history.load_showstyle_records(op_session, source="operator")
    screen = screens.showstyle_screen(rows, data="operator", sel_mode="style", style=["2312"])
    assert screen.header == ["DATE", "00002+&+Ope1", "00003+&+Ope2"]
    assert screen.rows == [["2025.10.01", "2312", "2312"]]


def test_showstyle_endpoint(client):
    response = client.get("/api/screens/showstyle", params={"data": "operator"})
    assert response.status_code == 200
    body = response.json()
    assert body["header"][0] == "DATE"
    assert len(body["rows"]) == 1

    csv_response = client.get(
        "/api/screens/showstyle.csv", params={"data": "shift", "sel_mode": "style"}
    )
    assert csv_response.status_code == 200
    assert csv_response.text.splitlines()[0].startswith("SHIFT,2312,1420")
