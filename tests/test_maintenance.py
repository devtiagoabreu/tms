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
