from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import tms.models  # noqa: F401
from tms.db.base import Base
from tms.ingest import cli
from tms.ingest.pipeline import preview_directory

FIXTURES = Path(__file__).parent / "fixtures"


def _text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _make_data_dir(tmp_path: Path) -> Path:
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
    return tmp_path


def test_preview_directory(tmp_path):
    stats = preview_directory(_make_data_dir(tmp_path))
    assert stats.files == 4
    assert stats.machines == 3
    assert stats.snapshots == 3
    assert stats.shift_schedules == 1
    assert stats.daily_raw == 2
    assert stats.agg_shift == 2
    assert stats.stop_events == 4


def test_preview_sources_filter(tmp_path):
    stats = preview_directory(_make_data_dir(tmp_path), sources="shift")
    assert stats.files == 1
    assert stats.daily_raw == 2
    assert stats.snapshots == 0
    assert stats.stop_events == 0


def test_cli_dry_run(tmp_path, capsys):
    code = cli.main([str(_make_data_dir(tmp_path)), "--dry-run"])
    assert code == 0
    out = capsys.readouterr().out
    assert "[dry-run]" in out
    assert "daily_raw             : 2" in out
    assert "stop_events           : 4" in out


def test_cli_ingests_into_sqlite(tmp_path):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)

    code = cli.main([str(_make_data_dir(tmp_path))], session_factory=factory)
    assert code == 0

    db = factory()
    from tms.models.runtime import AggShift, DailyRaw, StopEvent

    assert db.query(DailyRaw).count() == 2
    assert db.query(AggShift).count() == 2
    assert db.query(StopEvent).count() == 4
    db.close()


def test_cli_unknown_source(tmp_path, capsys):
    code = cli.main([str(_make_data_dir(tmp_path)), "--dry-run", "--sources", "bogus"])
    assert code == 2
    assert "fonte desconhecida" in capsys.readouterr().err
