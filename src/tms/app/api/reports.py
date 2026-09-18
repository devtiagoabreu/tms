"""Endpoints de relatórios agregados por período (dia/semana/mês)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from tms.app.api.schemas import PeriodRowOut
from tms.core.formulas import UNIT_PICK
from tms.db.base import get_db
from tms.reporting import PERIODS, WEEK_START
from tms.reporting import csv as csv_export
from tms.reporting import periods as reporting

router = APIRouter(prefix="/api/reports", tags=["reports"])

Limit = Query(500, ge=1, le=5000)
Offset = Query(0, ge=0)


def _fetch(
    db: Session,
    period: str,
    *,
    key: str | None,
    mac_name: str | None,
    day_from: str | None,
    day_to: str | None,
    week_start: int,
    min_run_tm: float,
    min_effic: float,
    unit: int,
    beam_type: int,
) -> list[reporting.PeriodRow]:
    if period not in PERIODS:
        raise HTTPException(status_code=404, detail=f"período inválido: {period}")
    return reporting.report(
        db,
        period,
        key=key,
        day_from=day_from,
        day_to=day_to,
        mac_name=mac_name,
        week_start=week_start,
        min_run_tm=min_run_tm,
        min_effic=min_effic,
        unit=unit,
        beam_type=beam_type,
    )


@router.get("/{period}.csv")
def report_period_csv(
    period: str,
    key: str | None = None,
    mac_name: str | None = None,
    day_from: str | None = None,
    day_to: str | None = None,
    week_start: int = Query(WEEK_START, ge=0, le=6),
    min_run_tm: float = Query(0.0, ge=0),
    min_effic: float = Query(0.0, ge=0, le=100),
    unit: int = Query(UNIT_PICK, ge=0, le=2),
    beam_type: int = Query(1, ge=1, le=2),
    db: Session = Depends(get_db),
) -> Response:
    """Exporta o relatório agregado em CSV."""
    rows = _fetch(
        db,
        period,
        key=key,
        mac_name=mac_name,
        day_from=day_from,
        day_to=day_to,
        week_start=week_start,
        min_run_tm=min_run_tm,
        min_effic=min_effic,
        unit=unit,
        beam_type=beam_type,
    )
    content = csv_export.write_csv(rows, unit=unit, beam_type=beam_type)
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="tms-{period}.csv"'},
    )


def _to_out(row: reporting.PeriodRow, unit: int, beam_type: int) -> PeriodRowOut:
    return PeriodRowOut(
        period=row.period,
        key=row.key,
        mac_name=row.mac_name,
        mac_type=row.mac_type,
        style=row.style,
        beam=row.beam,
        ubeam=row.ubeam,
        seisan=row.seisan,
        off_prod=row.off_prod,
        production=row.production(unit),
        run_tm=row.run_tm,
        stop_ttm=row.stop_ttm,
        effic=row.effic,
        rpm=row.rpm,
        total_ct=row.total_ct(beam_type),
        stop_ct=row.stop_ct,
        stop_tm=row.stop_tm,
        wf1_ct=row.wf1_ct,
        wf1_tm=row.wf1_tm,
        wf2_ct=row.wf2_ct,
        wf2_tm=row.wf2_tm,
        lh_ct=row.lh_ct,
        lh_tm=row.lh_tm,
    )


@router.get("/{period}", response_model=list[PeriodRowOut])
def report_period(
    period: str,
    key: str | None = None,
    mac_name: str | None = None,
    day_from: str | None = None,
    day_to: str | None = None,
    week_start: int = Query(WEEK_START, ge=0, le=6),
    min_run_tm: float = Query(0.0, ge=0),
    min_effic: float = Query(0.0, ge=0, le=100),
    unit: int = Query(UNIT_PICK, ge=0, le=2),
    beam_type: int = Query(1, ge=1, le=2),
    limit: int = Limit,
    offset: int = Offset,
    db: Session = Depends(get_db),
) -> list[PeriodRowOut]:
    """Agrega `daily_raw` por dia/semana/mês (sem médias; recomputa taxas)."""
    rows = _fetch(
        db,
        period,
        key=key,
        mac_name=mac_name,
        day_from=day_from,
        day_to=day_to,
        week_start=week_start,
        min_run_tm=min_run_tm,
        min_effic=min_effic,
        unit=unit,
        beam_type=beam_type,
    )
    return [_to_out(r, unit, beam_type) for r in rows[offset : offset + limit]]
