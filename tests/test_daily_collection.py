from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

import tms.models  # noqa: F401  (registra as tabelas no metadata)
from tms.core.live import LiveStatus, error_status
from tms.db.base import Base
from tms.models.daily import DailyCollectionItem, DailyCollectionRun, DailyLoomData
from tms.models.masters import Machine
from tms.models.runtime import AggShift, LiveStatusRecord
from tms.services import daily_collection

DAY = date(2026, 10, 27)


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.add_all(
        [
            Machine(mac_name="00001", mac_type="JAT", ip_addr="10.0.0.1"),
            Machine(mac_name="00002", mac_type="JAT", ip_addr="10.0.0.2"),
            Machine(mac_name="00003", mac_type="LWT", ip_addr=None),
        ]
    )
    session.commit()
    try:
        yield session
    finally:
        session.close()


def _live(rpm=500.0, style="1210"):
    return LiveStatus(
        mac_type="JAT710",
        bits={},
        data={"rpm": rpm, "effic_shift": 88.0, "run_time": 900.0, "stop_time": 60.0, "stop_shift": 4},
        setup={"style": style},
        scnt=5,
        dcnt=13,
        vcnt=2,
    )


def _seed_history(db, machine_id: int):
    start = datetime.combine(DAY, datetime.min.time()) + timedelta(hours=8)
    db.add_all(
        [
            LiveStatusRecord(
                machine_id=machine_id,
                collected_at=start,
                state="run",
                status="Run",
                rpm=500.0,
                efficiency=90.0,
                bits={},
                data={"run_time": 900.0, "stop_time": 60.0, "stop_shift": 3},
                setup={"style": "1210"},
            ),
            LiveStatusRecord(
                machine_id=machine_id,
                collected_at=start + timedelta(minutes=1),
                state="stopped",
                status="Weft",
                rpm=490.0,
                efficiency=88.5,
                bits={"weft": 1},
                data={"run_time": 900.0, "stop_time": 61.0, "stop_shift": 4},
                setup={"style": "1210"},
            ),
            LiveStatusRecord(
                machine_id=machine_id,
                collected_at=start + timedelta(minutes=3),
                state="stopped",
                status="Weft",
                rpm=490.0,
                efficiency=88.0,
                bits={"weft": 1},
                data={"run_time": 901.0, "stop_time": 63.0, "stop_shift": 4},
                setup={"style": "1210"},
            ),
            LiveStatusRecord(
                machine_id=machine_id,
                collected_at=start + timedelta(minutes=4),
                state="run",
                status="Run",
                rpm=505.0,
                efficiency=89.0,
                bits={},
                data={"run_time": 902.0, "stop_time": 63.0, "stop_shift": 4},
                setup={"style": "1210"},
            ),
        ]
    )
    db.commit()


def test_collects_once_per_day_and_uses_history(db, monkeypatch):
    monkeypatch.setattr(daily_collection, "fetch_live", lambda ip, timeout=0: _live())
    _seed_history(db, 1)

    run = daily_collection.collect_daily_data(db, DAY)
    assert run.status == "partial"  # 00002 ok, 00003 sem IP
    assert run.success_count == 2
    assert run.retry_count == 1

    rows = db.execute(select(DailyLoomData)).scalars().all()
    assert len(rows) == 2
    row = next(r for r in rows if r.mac_name == "00001")
    assert row.source == "history"
    assert row.rpm == pytest.approx((500 + 490 + 490 + 505) / 4)
    assert row.efficiency == pytest.approx((90 + 88.5 + 88 + 89) / 4)
    assert row.trama_stops == 1
    assert row.trama_stops_min == pytest.approx(3.0)
    assert row.total_stop_ct == 4

    # Segunda execucao nao cria outra execucao nem duplica linhas.
    again = daily_collection.collect_daily_data(db, DAY)
    assert again.id == run.id
    assert db.query(DailyCollectionRun).count() == 1
    assert db.query(DailyLoomData).count() == 2


def test_offline_loom_goes_to_retry_queue_then_collects(db, monkeypatch):
    monkeypatch.setattr(
        daily_collection, "fetch_live", lambda ip, timeout=0: error_status(100)
    )
    run = daily_collection.collect_daily_data(db, DAY)
    assert run.status == "failed"
    assert run.retry_count == 3  # 00001 e 00002 fora do ar; 00003 sem IP

    item = db.execute(
        select(DailyCollectionItem).where(DailyCollectionItem.mac_name == "00002")
    ).scalar_one()
    assert item.in_retry_queue is True
    assert "Power_off" in item.error_reason

    monkeypatch.setattr(daily_collection, "fetch_live", lambda ip, timeout=0: _live(rpm=610.0))
    retried = daily_collection.retry_pending(
        db, DAY, respect_interval=False, allow_live=True
    )
    assert retried.status == "partial"
    assert retried.retry_count == 1  # only 00003 (sem IP) remains

    row = db.execute(
        select(DailyLoomData).where(DailyLoomData.mac_name == "00002")
    ).scalar_one()
    assert row.rpm == 610.0
    assert row.source == "live"


def _agg_for(day: date, machine_id: int = 1) -> AggShift:
    return AggShift(
        shift_id=f"{day:%Y.%m.%d}.0",
        machine_id=machine_id,
        style="ABC",
        seisan_1=100.0,
        seisan_2=50.0,
        seisan_3=None,
        run_tm=420.0,
        stop_ttm=20.0,
        stop_ct=[1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        stop_tm=[2.0, 2.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    )


def test_backfill_past_days_marks_gap_without_live_read(db, monkeypatch):
    calls = []

    def fake_fetch(ip, timeout=0):
        calls.append(ip)
        return _live()

    monkeypatch.setattr(daily_collection, "fetch_live", fake_fetch)

    end = date.today() - timedelta(days=2)
    start = end - timedelta(days=1)
    runs = daily_collection.backfill(db, start, end)

    assert [r.collection_date for r in runs] == [start, end]
    assert all(r.status == "no_source" for r in runs)
    assert calls == []  # dia passado nunca consulta o tear ao vivo

    items = db.execute(select(DailyCollectionItem)).scalars().all()
    assert len(items) == 6
    assert {i.status for i in items} == {"no_source"}
    assert {i.error_reason for i in items} == {"Sem fonte de dados para este dia"}
    assert all(i.in_retry_queue is False for i in items)


def test_past_day_uses_stored_source_without_live_read(db, monkeypatch):
    calls = []
    monkeypatch.setattr(
        daily_collection,
        "fetch_live",
        lambda ip, timeout=0: calls.append(ip) or _live(),
    )
    db.add(_agg_for(DAY))
    db.commit()

    run = daily_collection.collect_daily_data(db, DAY, allow_live=False)

    assert calls == []
    assert run.status == "partial"
    assert run.success_count == 1

    item = db.execute(
        select(DailyCollectionItem).where(DailyCollectionItem.mac_name == "00001")
    ).scalar_one()
    assert item.status == "success"
    row = db.execute(
        select(DailyLoomData).where(DailyLoomData.mac_name == "00001")
    ).scalar_one()
    assert row.source == "agg_shift"


def test_retry_of_past_day_never_reads_live(db, monkeypatch):
    calls = []
    monkeypatch.setattr(
        daily_collection,
        "fetch_live",
        lambda ip, timeout=0: calls.append(ip) or error_status(100),
    )
    run = daily_collection.collect_daily_data(db, DAY, allow_live=True)
    assert run.retry_count == 3
    calls.clear()

    retried = daily_collection.retry_pending(db, DAY, respect_interval=False)

    assert calls == []  # retentativa de dia passado só olha fontes históricas
    assert retried.status == "no_source"
    assert retried.retry_count == 0


def test_recollect_past_day_picks_up_late_source(db):
    first = daily_collection.collect_daily_data(db, DAY, allow_live=False)
    assert first.status == "no_source"

    _seed_history(db, 1)
    second = daily_collection.collect_daily_data(db, DAY, allow_live=False)

    assert second.id == first.id
    assert second.success_count == 1
    assert second.status == "partial"
    row = db.execute(
        select(DailyLoomData).where(DailyLoomData.mac_name == "00001")
    ).scalar_one()
    assert row.source == "history"


def test_collection_gaps_reports_missing_days_and_looms(db):
    db.add(_agg_for(DAY))
    db.commit()
    daily_collection.collect_daily_data(db, DAY, allow_live=False)

    gaps = daily_collection.collection_gaps(db, days=2, end=DAY)

    assert gaps["start"] == (DAY - timedelta(days=1)).isoformat()
    assert gaps["end"] == DAY.isoformat()
    rows = {row["date"]: row for row in gaps["days"]}
    assert rows[DAY.isoformat()]["status"] == "partial"
    assert rows[DAY.isoformat()]["missing"] == ["00002", "00003"]

    previous = (DAY - timedelta(days=1)).isoformat()
    assert rows[previous]["status"] == "missing"
    assert set(rows[previous]["missing"]) == {"00001", "00002", "00003"}

    looms = {row["mac_name"]: row for row in gaps["looms"]}
    assert looms["00001"]["missing_count"] == 1
    assert looms["00002"]["missing_days"] == [previous, DAY.isoformat()]
    assert looms["00003"]["missing_count"] == 2


def test_ensure_recent_runs_is_idempotent(db, monkeypatch):
    monkeypatch.setattr(daily_collection, "fetch_live", lambda ip, timeout=0: _live())

    first = daily_collection.ensure_recent_runs(db, days=2)
    assert len(first) == 2

    again = daily_collection.ensure_recent_runs(db, days=2)
    assert again == []
    assert db.query(DailyCollectionRun).count() == 2


def test_agg_shift_has_priority_for_stop_breakdown(db, monkeypatch):
    monkeypatch.setattr(daily_collection, "fetch_live", lambda ip, timeout=0: _live())
    stop_ct = [1, 2, 0, 0, 0, 3, 0, 0, 0, 0, 4, 0]
    stop_tm = [2.0, 4.0, 0.0, 0.0, 0.0, 6.0, 0.0, 0.0, 0.0, 0.0, 8.0, 0.0]
    db.add(
        AggShift(
            shift_id=f"{DAY:%Y.%m.%d}.0",
            machine_id=1,
            style="ABC",
            seisan_1=100.0,
            seisan_2=50.0,
            seisan_3=None,
            run_tm=420.0,
            stop_ttm=20.0,
            stop_ct=stop_ct,
            stop_tm=stop_tm,
        )
    )
    db.commit()

    daily_collection.collect_daily_data(db, DAY)
    row = db.execute(
        select(DailyLoomData).where(DailyLoomData.mac_name == "00001")
    ).scalar_one()
    assert row.source == "agg_shift"
    assert row.style == "ABC"
    assert row.production == 150.0
    assert row.picks == 100.0
    assert row.meters == 50.0
    assert row.trama_stops == 3
    assert row.trama_stops_min == 6.0
    assert row.urdume_stops == 3
    assert row.urdume_stops_min == 6.0
    assert row.outros_stops == 4
    assert row.outros_stops_min == 8.0
    assert row.total_stop_ct == 10


def _ts(day: date) -> str:
    return f"{day.year} {day.month} {day.day} 3 6 0 0"


def _monitor_payload(day: date, *, with_history: bool = True) -> str:
    """Payload mínimo com d0/d1 e produção diária (PM_yN_p5)."""
    next_day = day + timedelta(days=1)
    lines = [
        "get_time 2026 11 5 3 12 0 0",
        "JAT710-TMS-DATA current",
        "mac_name 00001",
        "style 1210",
        "#end_of_data",
    ]
    if with_history:
        lines += [
            "JAT710-TMS-DATA stop_history",
            f"MH_d0_tm {_ts(next_day)}",
            "MH_d0_h0_history 10:00:00 10:05:00 0004",
            f"MH_d1_tm {_ts(day)}",
            "MH_d1_h0_history 11:00:00 11:02:00 0000",
            "MH_d1_h1_history 12:00:00 12:03:00 0004",
            "#end_of_data",
        ]
    lines += [
        "JAT700-MCARD-DATA moni_monitor",
        "PM_y1_p5_seisan 100 80 90 0",
        f"PM_y1_pd_tm {_ts(next_day)}",
        "PM_y2_p5_seisan 300 250 270 0",
        f"PM_y2_pd_tm {_ts(day)}",
        "#end_of_data",
    ]
    return "\n".join(lines)


def test_loom_history_preenche_breakdown_e_producao_do_dia_anterior_ao_ontem(
    db, monkeypatch
):
    day = date.today() - timedelta(days=2)
    db.add(
        DailyLoomData(
            collection_date=day,
            machine_id=1,
            mac_name="00001",
            source="live",
            total_stop_ct=2,
            collected_at=datetime.utcnow(),
        )
    )
    db.commit()
    monkeypatch.setattr(
        daily_collection,
        "fetch_monitor_data",
        lambda ip, timeout=0: type("Monitor", (), {"text": _monitor_payload(day)})(),
    )

    run = daily_collection.collect_daily_data(db, day, allow_live=False)

    assert run.collection_date == day
    row = db.execute(
        select(DailyLoomData).where(
            DailyLoomData.machine_id == 1,
            DailyLoomData.collection_date == day,
        )
    ).scalar_one()
    assert row.source == "loom_history"
    assert row.trama_stops == 1
    assert row.urdume_stops == 1
    assert row.outros_stops == 0
    assert row.picks == 30.0
    assert row.meters == 25.0


def test_loom_history_producao_sem_eventos_de_parada(db, monkeypatch):
    day = date.today() - timedelta(days=1)
    monkeypatch.setattr(
        daily_collection,
        "fetch_monitor_data",
        lambda ip, timeout=0: type(
            "Monitor", (), {"text": _monitor_payload(day, with_history=False)}
        )(),
    )

    daily_collection.collect_daily_data(db, day, allow_live=False)

    row = db.execute(
        select(DailyLoomData).where(
            DailyLoomData.machine_id == 1,
            DailyLoomData.collection_date == day,
        )
    ).scalar_one()
    assert row.source == "loom_history"
    assert row.picks == 30.0
    assert row.meters == 25.0
    assert row.total_stop_ct is None
