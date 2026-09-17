from datetime import datetime, time
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

import tms.models  # noqa: F401  (registra as tabelas no metadata)
from tms.db.base import Base
from tms.ingest import pipeline
from tms.ingest.shift_file import ShiftRecord
from tms.models.masters import Machine, Operator, ShiftSchedule
from tms.models.runtime import (
    AggShift,
    DailyRaw,
    MachineSnapshot,
    OperatorDaily,
    StopEvent,
)

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def _text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_ingest_current_idempotent(db):
    stats = pipeline.ingest_current(db, _text("current.txt"))
    db.commit()
    assert stats.machines == 2
    assert stats.snapshots == 2

    machine = db.execute(select(Machine).where(Machine.mac_name == "00001")).scalar_one()
    assert machine.mac_type == "JAT"
    assert machine.ip_addr == "172.17.1.1"

    snapshot = db.execute(
        select(MachineSnapshot).where(MachineSnapshot.machine_id == machine.id)
    ).scalar_one()
    assert snapshot.style == "1210"
    assert snapshot.s_beam == "90000 98416"
    assert snapshot.get_time == datetime(2026, 9, 17, 13, 58, 9)
    assert snapshot.raw["s_ubeam"] == [0, 0]

    again = pipeline.ingest_current(db, _text("current.txt"))
    db.commit()
    assert again.machines == 0
    assert again.snapshots == 0
    assert db.query(MachineSnapshot).count() == 2


def test_ingest_setting_creates_schedule(db):
    stats = pipeline.ingest_setting(db, _text("setting.txt"))
    db.commit()
    assert stats.machines == 1
    assert stats.shift_schedules == 1

    schedule = db.execute(select(ShiftSchedule)).scalar_one()
    assert schedule.code == "00001"
    assert schedule.shift_mode == 0
    assert schedule.day_start_time == "6:0"
    assert schedule.schedule_json["days"]["0"] == [
        "3", "06:14", "14:22", "22:06", "-1:-1", "-1:-1",
    ]
    assert schedule.schedule_json["names"]["1"] == "Anderson"

    machine = db.execute(select(Machine)).scalar_one()
    snapshot = db.execute(
        select(MachineSnapshot).where(MachineSnapshot.machine_id == machine.id)
    ).scalar_one()
    assert snapshot.rtc_time == datetime(2026, 9, 17, 10, 8, 5)


def test_ingest_shift_creates_daily_raw_and_agg(db):
    stats = pipeline.ingest_shift(db, _text("shift_2025.10.01.0.txt"), "2025.10.01.0")
    db.commit()
    assert stats.daily_raw == 2
    assert stats.agg_shift == 2

    machine = db.execute(select(Machine).where(Machine.mac_name == "00001")).scalar_one()
    raw = db.execute(
        select(DailyRaw).where(DailyRaw.machine_id == machine.id)
    ).scalar_one()
    assert raw.day == "2025.10.01"
    assert raw.shift_id == "2025.10.01.0"
    assert raw.run_tm == 23188
    assert raw.seisan["seisan"] == [2160, 939, 1027, 0]
    assert raw.raw_line.startswith("fixed,mac_name 00001")

    agg = db.execute(
        select(AggShift).where(AggShift.machine_id == machine.id)
    ).scalar_one()
    assert agg.seisan_1 == pytest.approx(216.0)
    assert agg.run_tm == pytest.approx(23188 / 60.0)
    assert agg.effic == pytest.approx(23188 * 100.0 / (23188 + 6812))

    again = pipeline.ingest_shift(db, _text("shift_2025.10.01.0.txt"), "2025.10.01.0")
    db.commit()
    assert again.daily_raw == 0
    assert db.query(DailyRaw).count() == 2
    assert db.query(AggShift).count() == 2


def test_build_agg_matches_legacy_shift_shiftshift():
    """Confere o cálculo 40→12 contra um agregado real (00004, 2026.07.01.0)."""
    record = ShiftRecord(
        mac_name="00004",
        mac_type="JAT",
        style="2620",
        beam="4782",
        seisan=[3092, 1189, 1300, 0],
        off_prod=[0, 0, 0, 0],
        run_tm_sec=28224,
        stop_ttm_sec=1758,
        s_ct=[2, 0, 0, 0, 1, 2, 2, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
              0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1],
        s_tm=[406, 0, 0, 0, 216, 331, 367, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
              0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
              438, 2419],
    )
    agg = pipeline.build_agg(record, "2026.07.01.0")
    assert agg.seisan_1 == pytest.approx(309.2)
    assert agg.seisan_2 == pytest.approx(118.9)
    assert agg.seisan_3 == pytest.approx(130.0)
    assert agg.run_tm == pytest.approx(470.400)
    assert agg.stop_ttm == pytest.approx(29.300)
    assert agg.stop_ct == [0, 2, 0, 0, 0, 4, 0, 0, 1, 1, 0, 0]
    assert agg.stop_tm == pytest.approx(
        [0, 6.767, 0, 0, 0, 11.633, 0, 0, 3.600, 40.317, 7.300, 0], abs=1e-3
    )
    assert agg.wf1_ct == [2, 2, 0, 0, 0, 0]
    assert agg.wf1_tm == pytest.approx([5.517, 6.117, 0, 0, 0, 0], abs=1e-3)
    assert agg.wf2_ct == [0, 0, 0, 0, 0, 0]
    assert agg.lh_ct == [0, 0, 0, 0, 0, 0]


def test_ingest_stophistory_replaces_day(db):
    stats = pipeline.ingest_stophistory(db, _text("stop_history_00000001.txt"))
    db.commit()
    assert stats.stop_events == 4

    machine = db.execute(select(Machine).where(Machine.mac_name == "00001")).scalar_one()
    events = db.execute(
        select(StopEvent).where(StopEvent.machine_id == machine.id).order_by(StopEvent.id)
    ).scalars().all()
    assert len(events) == 4

    stopped = events[0]
    assert stopped.day == "2026.07.01"
    assert stopped.raw_code == "2153"
    assert stopped.stop_time == 6 * 3600 + 36 * 60 + 9
    assert stopped.run_time == 0
    assert stopped.stop_start == datetime(2026, 7, 1, 6, 36, 9)
    assert stopped.stop_end is None
    assert stopped.duration_min is None

    running = events[1]
    assert running.raw_code == "0027"
    assert running.stop_time == 0
    assert running.run_time == 10 * 3600 + 8 * 60 + 59

    both = events[2]
    assert both.duration_min == pytest.approx(3 + 50 / 60)

    again = pipeline.ingest_stophistory(db, _text("stop_history_00000001.txt"))
    db.commit()
    assert again.stop_events == 4
    assert db.query(StopEvent).count() == 4


def test_ingest_operator_creates_operator_and_daily(db):
    stats = pipeline.ingest_operator(db, _text("operator_2025.10.01.txt"))
    db.commit()
    assert stats.machines == 2
    assert stats.operators == 1  # ambos ope_num 0
    assert stats.operator_daily == 2

    operator = db.execute(select(Operator)).scalar_one()
    assert operator.code == "0"
    assert operator.name == "A"  # último nome visto

    machine = db.execute(select(Machine).where(Machine.mac_name == "00002")).scalar_one()
    job = db.execute(
        select(OperatorDaily).where(OperatorDaily.machine_id == machine.id)
    ).scalar_one()
    assert job.day == "2025.10.01"
    assert job.run_tm == 72090
    assert job.seisan["seisan"] == [7067, 3156, 3452, 0]
    assert job.start_time == datetime(2025, 10, 1, 6, 0, 0)

    again = pipeline.ingest_operator(db, _text("operator_2025.10.01.txt"))
    db.commit()
    assert again.operator_daily == 0
    assert again.operators == 0
    assert db.query(OperatorDaily).count() == 2


def test_ingest_loom_creates_snapshot(db):
    stats = pipeline.ingest_loom(db, _text("loom_00001.txt"))
    db.commit()
    assert stats.machines == 1
    assert stats.snapshots == 1

    machine = db.execute(select(Machine)).scalar_one()
    assert machine.mac_name == "00001"
    assert machine.mac_type == "JAT"  # normalizado de JAT710

    snapshot = db.execute(select(MachineSnapshot)).scalar_one()
    assert snapshot.shift_id == "2026.09.17.1"
    assert snapshot.get_time == datetime(2026, 9, 17, 13, 58, 9)
    assert snapshot.sys_time == datetime(2026, 9, 17, 14, 8, 5)
    assert snapshot.style == "1210"
    assert snapshot.s_beam == "90000 98416"

    again = pipeline.ingest_loom(db, _text("loom_00001.txt"))
    db.commit()
    assert again.snapshots == 0
    assert db.query(MachineSnapshot).count() == 1


def test_ingest_directory(tmp_path, db):
    (tmp_path / "current").mkdir()
    (tmp_path / "current" / "current.txt").write_text(_text("current.txt"), encoding="utf-8")
    (tmp_path / "current" / "setting.txt").write_text(_text("setting.txt"), encoding="utf-8")
    (tmp_path / "shift").mkdir()
    (tmp_path / "shift" / "2025.10.01.0.txt").write_text(
        _text("shift_2025.10.01.0.txt"), encoding="utf-8"
    )
    (tmp_path / "stop_history" / "2026.07.01").mkdir(parents=True)
    (tmp_path / "stop_history" / "2026.07.01" / "00000001.txt").write_text(
        _text("stop_history_00000001.txt"), encoding="utf-8"
    )

    stats = pipeline.ingest_directory(db, tmp_path)
    assert stats.files == 4
    assert stats.snapshots == 3
    assert stats.daily_raw == 2
    assert stats.agg_shift == 2
    assert stats.stop_events == 4
    assert stats.shift_schedules == 1

    machine = db.execute(select(Machine).where(Machine.mac_name == "00001")).scalar_one()
    assert db.query(StopEvent).filter(StopEvent.machine_id == machine.id).count() == 4

    # reingestão não duplica
    pipeline.ingest_directory(db, tmp_path)
    assert db.query(DailyRaw).count() == 2
    assert db.query(AggShift).count() == 2
    assert db.query(StopEvent).count() == 4
    assert db.query(MachineSnapshot).count() == 3
