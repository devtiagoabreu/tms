from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

import tms.models  # noqa: F401  (registra as tabelas no metadata)
from tms import maintenance
from tms.db.base import Base
from tms.ingest import pipeline
from tms.models.runtime import AggShift, DailyRaw, MachineSnapshot, OperatorDaily, StopEvent

FIXTURES = Path(__file__).parent / "fixtures"


def _text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    pipeline.ingest_current(session, _text("current.txt"))
    pipeline.ingest_shift(session, _text("shift_2025.10.01.0.txt"), "2025.10.01.0")
    pipeline.ingest_stophistory(session, _text("stop_history_00000001.txt"))
    pipeline.ingest_operator(session, _text("operator_2025.10.01.txt"))
    pipeline.ingest_loom(session, _text("loom_00001.txt"))
    session.commit()
    try:
        yield session
    finally:
        session.close()


def test_purge_requires_bound(db):
    with pytest.raises(ValueError):
        maintenance.purge(db)


def test_purge_dry_run_does_not_delete(db):
    counts = maintenance.purge(db, day_to="2026.12.31", dry_run=True)
    assert counts["daily_raw"] == 2
    assert counts["agg_shift"] == 2
    assert counts["stop_events"] == 4
    assert counts["operator_daily"] == 2
    assert counts["machine_snapshots"] >= 1
    assert db.query(DailyRaw).count() == 2


def test_purge_selected_sources(db):
    counts = maintenance.purge(db, day_to="2026.12.31", sources=["stop_events", "operator_daily"])
    assert counts["stop_events"] == 4
    assert counts["operator_daily"] == 2
    assert db.query(StopEvent).count() == 0
    assert db.query(OperatorDaily).count() == 0
    assert db.query(DailyRaw).count() == 2


def test_rebuild_agg_from_daily_raw(db):
    db.execute(AggShift.__table__.delete())
    db.commit()
    assert db.query(AggShift).count() == 0

    stats = pipeline.rebuild_agg(db, day_from="2025.10.01", day_to="2025.10.01")
    db.commit()
    assert stats.agg_shift == 2
    assert db.query(AggShift).count() == 2

    row = db.execute(
        select(AggShift).where(AggShift.shift_id == "2025.10.01.0", AggShift.machine_id.is_not(None))
    ).scalars().first()
    assert row is not None
    assert len(row.stop_ct) == 12
    assert row.effic is not None


def test_cli_parser():
    args = maintenance.build_parser().parse_args(["purge", "--to", "2024.12.31", "--dry-run"])
    assert args.date_to == "2024.12.31"
    assert args.dry_run is True
    assert args.func is maintenance._cmd_purge


def test_months_ago():
    assert maintenance.months_ago("2026.09.17", 2) == "2026.07"
    assert maintenance.months_ago("2026.01.15", 2) == "2025.11"
    assert maintenance.months_ago("2026.09.17", 11) == "2025.10"


def test_retention_tiers(db):
    # mais novo = 2026.09.17 (current). raw (3m) corta em 2026.07.01;
    # agg (12m) corta em 2025.10.01; snapshot (1m) em 2026.09.01.
    dry = maintenance.retention(db, reference_day="2026.09.17", dry_run=True)
    assert dry["daily_raw"] == 2  # 2025.10.01 < 2026.07.01
    assert dry["stop_events"] == 0  # 2026.07.01 mantido
    assert dry["agg_shift"] == 0
    assert dry["operator_daily"] == 0
    assert dry["machine_snapshots"] == 0

    counts = maintenance.retention(db, reference_day="2026.09.17")
    assert counts["daily_raw"] == 2
    assert db.query(DailyRaw).count() == 0
    assert db.query(AggShift).count() == 2
    assert db.query(StopEvent).count() == 4


def test_retention_reference_auto(db):
    # âncora automática = registro mais novo do banco (2026.09.17)
    assert maintenance._newest_day(db) == "2026.09.17"
    counts = maintenance.retention(db)
    assert counts["daily_raw"] == 2


def test_cli_retention_parser():
    args = maintenance.build_parser().parse_args(
        ["retention", "--reference", "2026.09.17", "--raw-months", "0", "--dry-run"]
    )
    assert args.reference == "2026.09.17"
    assert args.raw_months == 0
    assert args.func is maintenance._cmd_retention


def test_report_from_agg_survives_raw_purge(db):
    from tms.reporting import periods as reporting

    agg_rows = {r.mac_name: r for r in reporting.report(db, "day", key="2025.10.01")}
    raw_rows = {r.mac_name: r for r in reporting.report(db, "day", key="2025.10.01", source="raw")}
    assert set(agg_rows) == set(raw_rows) == {"00001", "00005"}
    for name, raw in raw_rows.items():
        agg = agg_rows[name]
        assert agg.seisan[:3] == raw.seisan[:3]
        assert agg.run_tm == raw.run_tm
        assert agg.effic == pytest.approx(raw.effic)
        assert agg.stop_ct == raw.stop_ct

    # apaga o bruto; o relatório continua vindo de agg_shift (12 meses)
    db.execute(DailyRaw.__table__.delete())
    db.commit()
    assert db.query(DailyRaw).count() == 0
    after = reporting.report(db, "day", key="2025.10.01")
    assert {r.mac_name for r in after} == {"00001", "00005"}
