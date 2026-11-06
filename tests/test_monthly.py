from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import tms.models  # noqa: F401  (registra as tabelas no metadata)
from tms.db.base import Base
from tms.models.daily import DailyLoomData
from tms.services import monthly


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def _row(day: date, *, picks: float, meters: float) -> DailyLoomData:
    return DailyLoomData(
        collection_date=day,
        machine_id=1,
        mac_name="00001",
        source="loom_history",
        picks=picks,
        meters=meters,
        collected_at=datetime.utcnow(),
    )


def test_month_summary_soma_metras_e_pontos(db):
    start = date(2026, 10, 1)
    end = date(2026, 10, 31)
    db.add_all(
        [
            _row(start, picks=10.0, meters=8.0),
            _row(start + timedelta(days=1), picks=2.5, meters=3.5),
        ]
    )
    db.commit()

    result = monthly.month_summary(db, start, end, allow_legacy=False)

    assert result["points"] == 12.5
    assert result["meters"] == 11.5
    assert result["days"] == 2
    assert result["source"] == "daily"


def test_month_summary_usa_export_legado_quando_nao_ha_coleta(db, tmp_path, monkeypatch):
    monkeypatch.setattr(monthly, "LEGACY_ROOT", tmp_path)
    directory = tmp_path / "2026-10" / "daily"
    directory.mkdir(parents=True)
    (directory / "2026-10-02.csv").write_text(
        "\n".join(
            [
                "2026.10.02.A,00001,1210,None,123219,506,78.88,425.97,114.03,215.8,187.6,205.2,0",
                "2026.10.02.B,00001,1210,None,123219,506,78.52,451.52,123.48,228.9,199.1,217.6,0",
                "2026.10.03.A,00002,1820,None,Undefined,501,85.44,461.40,78.60,231.5,201.2,220.1,0",
            ]
        ),
        encoding="utf-8",
    )

    result = monthly.month_summary(
        db, date(2026, 10, 1), date(2026, 10, 31), allow_legacy=True
    )

    assert result["points"] == pytest.approx(1513.0)
    assert result["meters"] == pytest.approx(587.9)
    assert result["days"] == 2
    assert result["source"] == "legacy_csv"


def test_current_and_previous_months():
    (current_start, current_end), (previous_start, previous_end) = (
        monthly.current_and_previous_months(date(2026, 11, 5))
    )
    assert (current_start, current_end) == (date(2026, 11, 1), date(2026, 11, 5))
    assert (previous_start, previous_end) == (date(2026, 10, 1), date(2026, 10, 31))
