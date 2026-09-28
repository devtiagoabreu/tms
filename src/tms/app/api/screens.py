"""Telas de relatório (Fase 3): efficiency, production, stop-analysis,
shiftreport e stylereport.

Endpoints JSON e CSV nos modos tear/estilo (``mode=shift``) e operador
(``mode=operator``); períodos shift/day/week/month. O stylereport agrega
por estilo (``mode=style``) e o shiftreport segue sel item2/item/item3/detail
das preferências (``report_prefs``).
"""

from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from tms import config_service as cfg
from tms.core.formulas import UNIT_PICK
from tms.db.base import get_db
from tms.reporting import PERIODS, WEEK_START
from tms.reporting import history
from tms.reporting import periods as reporting
from tms.reporting import screens

router = APIRouter(prefix="/api/screens", tags=["screens"])

Period = Query("day", description="shift | day | week | month")
WeekStart = Query(WEEK_START, ge=0, le=6)
Mode = Query("shift", pattern="^(shift|operator)$")


def Sel() -> Query:
    """Query compartilhada para a seleção shred (loom|style).

    Uma instância única global seria mutável: o primeiro endpoint que a
    usasse fixaria o alias (``sel`` no shiftreport) e os demais (``sel_mode``)
    passariam a ignorar o parâmetro. Uma fábrica retorna um Query novo a cada
    chamada, preservando o nome do parâmetro de cada rota.
    """
    return Query("loom", pattern="^(loom|style)$")


HistoryData = Query("shift", pattern="^(shift|operator)$")


def _rows(
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
    mode: str,
) -> list[reporting.PeriodRow]:
    if period not in PERIODS:
        raise HTTPException(status_code=404, detail=f"período inválido: {period}")
    try:
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
            mode=mode,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


def _csv_response(screen: screens.Screen, filename: str) -> Response:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(screen.header)
    writer.writerows(screen.rows)
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _screen_out(screen: screens.Screen) -> dict:
    return {
        "period_type": screen.period_type,
        "header": screen.header,
        "rows": screen.rows,
    }


def _history_rows(
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
    sel_mode: str,
    loom: list[str] | None,
    style: list[str] | None,
) -> list[reporting.PeriodRow]:
    """Linhas do statushistory/svsreport: relatório por tear/estilo já filtrado
    pelo `sel_mode` (lista de teares ou de estilos, como no legado)."""
    rows = _rows(db, period, key=key, mac_name=mac_name, day_from=day_from,
                 day_to=day_to, week_start=week_start, min_run_tm=min_run_tm,
                 min_effic=min_effic, mode="shift")
    if sel_mode == "loom" and loom:
        wanted = set(loom)
        rows = [r for r in rows if r.mac_name in wanted]
    elif sel_mode == "style" and style:
        wanted = set(style)
        rows = [r for r in rows if (r.style or "") in wanted]
    return rows


# --------------------------------------------------------------- efficiency --

@router.get("/efficiency")
def efficiency(
    db: Session = Depends(get_db),
    period: str = Period,
    mode: str = Mode,
    key: str | None = None,
    mac_name: str | None = None,
    day_from: str | None = None,
    day_to: str | None = None,
    week_start: int = WeekStart,
    min_run_tm: float = Query(0.0, ge=0),
    min_effic: float = Query(0.0, ge=0, le=100),
) -> dict:
    rows = _rows(db, period, key=key, mac_name=mac_name, day_from=day_from, day_to=day_to,
                 week_start=week_start, min_run_tm=min_run_tm, min_effic=min_effic, mode=mode)
    return _screen_out(screens.efficiency_screen(rows, period, mode))


@router.get("/efficiency.csv")
def efficiency_csv(
    db: Session = Depends(get_db),
    period: str = Period,
    mode: str = Mode,
    key: str | None = None,
    mac_name: str | None = None,
    day_from: str | None = None,
    day_to: str | None = None,
    week_start: int = WeekStart,
    min_run_tm: float = Query(0.0, ge=0),
    min_effic: float = Query(0.0, ge=0, le=100),
) -> Response:
    rows = _rows(db, period, key=key, mac_name=mac_name, day_from=day_from, day_to=day_to,
                 week_start=week_start, min_run_tm=min_run_tm, min_effic=min_effic, mode=mode)
    return _csv_response(screens.efficiency_screen(rows, period, mode), "tms-efficiency.csv")


# --------------------------------------------------------------- production --

@router.get("/production")
def production(
    db: Session = Depends(get_db),
    period: str = Period,
    mode: str = Mode,
    key: str | None = None,
    mac_name: str | None = None,
    day_from: str | None = None,
    day_to: str | None = None,
    week_start: int = WeekStart,
    min_run_tm: float = Query(0.0, ge=0),
    min_effic: float = Query(0.0, ge=0, le=100),
    unit: int = Query(UNIT_PICK, ge=0, le=2),
) -> dict:
    rows = _rows(db, period, key=key, mac_name=mac_name, day_from=day_from, day_to=day_to,
                 week_start=week_start, min_run_tm=min_run_tm, min_effic=min_effic, mode=mode)
    return _screen_out(screens.production_screen(rows, period, unit, mode))


@router.get("/production.csv")
def production_csv(
    db: Session = Depends(get_db),
    period: str = Period,
    mode: str = Mode,
    key: str | None = None,
    mac_name: str | None = None,
    day_from: str | None = None,
    day_to: str | None = None,
    week_start: int = WeekStart,
    min_run_tm: float = Query(0.0, ge=0),
    min_effic: float = Query(0.0, ge=0, le=100),
    unit: int = Query(UNIT_PICK, ge=0, le=2),
) -> Response:
    rows = _rows(db, period, key=key, mac_name=mac_name, day_from=day_from, day_to=day_to,
                 week_start=week_start, min_run_tm=min_run_tm, min_effic=min_effic, mode=mode)
    return _csv_response(screens.production_screen(rows, period, unit, mode), "tms-production.csv")


# ------------------------------------------------------------ stop-analysis --

@router.get("/stop-analysis")
def stop_analysis(
    db: Session = Depends(get_db),
    period: str = Period,
    mode: str = Mode,
    key: str | None = None,
    mac_name: str | None = None,
    day_from: str | None = None,
    day_to: str | None = None,
    week_start: int = WeekStart,
    min_run_tm: float = Query(0.0, ge=0),
    min_effic: float = Query(0.0, ge=0, le=100),
    beam_type: int = Query(1, ge=1, le=2),
) -> dict:
    rows = _rows(db, period, key=key, mac_name=mac_name, day_from=day_from, day_to=day_to,
                 week_start=week_start, min_run_tm=min_run_tm, min_effic=min_effic, mode=mode)
    prefs = cfg.get_report_prefs(db)
    count = screens.stop_analysis_screen(rows, prefs, period=period, beam_type=beam_type,
                                         time=False, mode=mode)
    time = screens.stop_analysis_screen(rows, prefs, period=period, beam_type=beam_type,
                                        time=True, mode=mode)
    return {
        "period_type": count.period_type,
        "header": count.header,
        "count_rows": count.rows,
        "time_rows": time.rows,
    }


@router.get("/stop-analysis.csv")
def stop_analysis_csv(
    db: Session = Depends(get_db),
    period: str = Period,
    mode: str = Mode,
    key: str | None = None,
    mac_name: str | None = None,
    day_from: str | None = None,
    day_to: str | None = None,
    week_start: int = WeekStart,
    min_run_tm: float = Query(0.0, ge=0),
    min_effic: float = Query(0.0, ge=0, le=100),
    beam_type: int = Query(1, ge=1, le=2),
    value: str = Query("count", pattern="^(count|time)$"),
) -> Response:
    rows = _rows(db, period, key=key, mac_name=mac_name, day_from=day_from, day_to=day_to,
                 week_start=week_start, min_run_tm=min_run_tm, min_effic=min_effic, mode=mode)
    prefs = cfg.get_report_prefs(db)
    screen = screens.stop_analysis_screen(
        rows, prefs, period=period, beam_type=beam_type, time=(value == "time"), mode=mode
    )
    return _csv_response(screen, f"tms-stop-analysis-{value}.csv")


# -------------------------------------------------------------- shiftreport --

def _shiftreport_screen(db, rows, *, period, mode, sel, beam_type, unit) -> screens.Screen:
    prefs = cfg.get_report_prefs(db)
    if period is None:
        period = prefs["period"]
    if beam_type is None:
        beam_type = prefs["beam_type"]
    if unit is None:
        unit = prefs["unit"]
    jat_ari, lwt_ari = reporting.machine_aris(db)
    return screens.shiftreport_screen(
        rows, prefs, period=period, sel=sel, beam_type=beam_type, unit=unit,
        mode=mode, jat_ari=jat_ari, lwt_ari=lwt_ari,
    )


@router.get("/shiftreport")
def shiftreport(
    db: Session = Depends(get_db),
    period: str | None = None,
    mode: str = Mode,
    sel: str = Sel(),
    key: str | None = None,
    mac_name: str | None = None,
    day_from: str | None = None,
    day_to: str | None = None,
    week_start: int = WeekStart,
    min_run_tm: float = Query(0.0, ge=0),
    min_effic: float = Query(0.0, ge=0, le=100),
    beam_type: int | None = Query(None, ge=1, le=2),
    unit: int | None = Query(None, ge=0, le=2),
) -> dict:
    period = period or cfg.get_report_prefs(db)["period"]
    rows = _rows(db, period, key=key, mac_name=mac_name, day_from=day_from,
                 day_to=day_to, week_start=week_start, min_run_tm=min_run_tm,
                 min_effic=min_effic, mode=mode)
    return _screen_out(_shiftreport_screen(
        db, rows, period=period, mode=mode, sel=sel, beam_type=beam_type, unit=unit)
    )


@router.get("/shiftreport.csv")
def shiftreport_csv(
    db: Session = Depends(get_db),
    period: str | None = None,
    mode: str = Mode,
    sel: str = Sel(),
    key: str | None = None,
    mac_name: str | None = None,
    day_from: str | None = None,
    day_to: str | None = None,
    week_start: int = WeekStart,
    min_run_tm: float = Query(0.0, ge=0),
    min_effic: float = Query(0.0, ge=0, le=100),
    beam_type: int | None = Query(None, ge=1, le=2),
    unit: int | None = Query(None, ge=0, le=2),
) -> Response:
    period = period or cfg.get_report_prefs(db)["period"]
    rows = _rows(db, period, key=key, mac_name=mac_name, day_from=day_from,
                 day_to=day_to, week_start=week_start, min_run_tm=min_run_tm,
                 min_effic=min_effic, mode=mode)
    return _csv_response(_shiftreport_screen(
        db, rows, period=period, mode=mode, sel=sel, beam_type=beam_type, unit=unit),
        "tms-shiftreport.csv")


# -------------------------------------------------------------- stylereport --

def _stylereport_screen(db, rows, *, period, beam_type, unit) -> screens.Screen:
    prefs = cfg.get_report_prefs(db)
    if period is None:
        period = prefs["period"]
    if beam_type is None:
        beam_type = prefs["beam_type"]
    if unit is None:
        unit = prefs["unit"]
    return screens.stylereport_screen(
        rows, prefs, period=period, beam_type=beam_type, unit=unit,
    )


@router.get("/stylereport")
def stylereport(
    db: Session = Depends(get_db),
    period: str | None = None,
    key: str | None = None,
    mac_name: str | None = None,
    day_from: str | None = None,
    day_to: str | None = None,
    week_start: int = WeekStart,
    min_run_tm: float = Query(0.0, ge=0),
    min_effic: float = Query(0.0, ge=0, le=100),
    beam_type: int | None = Query(None, ge=1, le=2),
    unit: int | None = Query(None, ge=0, le=2),
) -> dict:
    period = period or cfg.get_report_prefs(db)["period"]
    rows = _rows(db, period, key=key, mac_name=mac_name, day_from=day_from,
                 day_to=day_to, week_start=week_start, min_run_tm=min_run_tm,
                 min_effic=min_effic, mode="style")
    return _screen_out(_stylereport_screen(
        db, rows, period=period, beam_type=beam_type, unit=unit)
    )


@router.get("/stylereport.csv")
def stylereport_csv(
    db: Session = Depends(get_db),
    period: str | None = None,
    key: str | None = None,
    mac_name: str | None = None,
    day_from: str | None = None,
    day_to: str | None = None,
    week_start: int = WeekStart,
    min_run_tm: float = Query(0.0, ge=0),
    min_effic: float = Query(0.0, ge=0, le=100),
    beam_type: int | None = Query(None, ge=1, le=2),
    unit: int | None = Query(None, ge=0, le=2),
) -> Response:
    period = period or cfg.get_report_prefs(db)["period"]
    rows = _rows(db, period, key=key, mac_name=mac_name, day_from=day_from,
                 day_to=day_to, week_start=week_start, min_run_tm=min_run_tm,
                 min_effic=min_effic, mode="style")
    return _csv_response(_stylereport_screen(
        db, rows, period=period, beam_type=beam_type, unit=unit),
        "tms-stylereport.csv")


# ------------------------------------------------------------- statushistory --

@router.get("/statushistory")
def statushistory(
    db: Session = Depends(get_db),
    period: str = Period,
    sel_mode: str = Sel(),
    loom: list[str] = Query(default=None),
    style: list[str] = Query(default=None),
    key: str | None = None,
    mac_name: str | None = None,
    day_from: str | None = None,
    day_to: str | None = None,
    week_start: int = WeekStart,
    min_run_tm: float = Query(0.0, ge=0),
    min_effic: float = Query(0.0, ge=0, le=100),
) -> dict:
    rows = _history_rows(
        db, period, key=key, mac_name=mac_name, day_from=day_from, day_to=day_to,
        week_start=week_start, min_run_tm=min_run_tm, min_effic=min_effic,
        sel_mode=sel_mode, loom=loom, style=style,
    )
    return _screen_out(screens.statushistory_screen(rows, period))


@router.get("/statushistory.csv")
def statushistory_csv(
    db: Session = Depends(get_db),
    period: str = Period,
    sel_mode: str = Sel(),
    loom: list[str] = Query(default=None),
    style: list[str] = Query(default=None),
    key: str | None = None,
    mac_name: str | None = None,
    day_from: str | None = None,
    day_to: str | None = None,
    week_start: int = WeekStart,
    min_run_tm: float = Query(0.0, ge=0),
    min_effic: float = Query(0.0, ge=0, le=100),
) -> Response:
    rows = _history_rows(
        db, period, key=key, mac_name=mac_name, day_from=day_from, day_to=day_to,
        week_start=week_start, min_run_tm=min_run_tm, min_effic=min_effic,
        sel_mode=sel_mode, loom=loom, style=style,
    )
    return _csv_response(screens.statushistory_screen(rows, period), "tms-statushistory.csv")


# ---------------------------------------------------------------- svsreport --

@router.get("/svsreport")
def svsreport(
    db: Session = Depends(get_db),
    period: str = Period,
    sel_mode: str = Sel(),
    loom: list[str] = Query(default=None),
    style: list[str] = Query(default=None),
    key: str | None = None,
    mac_name: str | None = None,
    day_from: str | None = None,
    day_to: str | None = None,
    week_start: int = WeekStart,
    min_run_tm: float = Query(0.0, ge=0),
    min_effic: float = Query(0.0, ge=0, le=100),
    beam_type: int = Query(1, ge=1, le=2),
) -> dict:
    rows = _history_rows(
        db, period, key=key, mac_name=mac_name, day_from=day_from, day_to=day_to,
        week_start=week_start, min_run_tm=min_run_tm, min_effic=min_effic,
        sel_mode=sel_mode, loom=loom, style=style,
    )
    prefs = cfg.get_report_prefs(db)
    return _screen_out(screens.svsreport_screen(
        rows, prefs, period=period, beam_type=beam_type)
    )


@router.get("/svsreport.csv")
def svsreport_csv(
    db: Session = Depends(get_db),
    period: str = Period,
    sel_mode: str = Sel(),
    loom: list[str] = Query(default=None),
    style: list[str] = Query(default=None),
    key: str | None = None,
    mac_name: str | None = None,
    day_from: str | None = None,
    day_to: str | None = None,
    week_start: int = WeekStart,
    min_run_tm: float = Query(0.0, ge=0),
    min_effic: float = Query(0.0, ge=0, le=100),
    beam_type: int = Query(1, ge=1, le=2),
) -> Response:
    rows = _history_rows(
        db, period, key=key, mac_name=mac_name, day_from=day_from, day_to=day_to,
        week_start=week_start, min_run_tm=min_run_tm, min_effic=min_effic,
        sel_mode=sel_mode, loom=loom, style=style,
    )
    prefs = cfg.get_report_prefs(db)
    return _csv_response(screens.svsreport_screen(
        rows, prefs, period=period, beam_type=beam_type),
        "tms-svsreport.csv")


# -------------------------------------------------------------- stophistory --

@router.get("/stophistory")
def stophistory(
    db: Session = Depends(get_db),
    day_from: str | None = None,
    day_to: str | None = None,
    mac_name: str | None = None,
) -> dict:
    return _screen_out(screens.stophistory_screen(
        history.load_stop_events(db, day_from=day_from, day_to=day_to, mac_name=mac_name)
    ))


@router.get("/stophistory.csv")
def stophistory_csv(
    db: Session = Depends(get_db),
    day_from: str | None = None,
    day_to: str | None = None,
    mac_name: str | None = None,
) -> Response:
    return _csv_response(screens.stophistory_screen(
        history.load_stop_events(db, day_from=day_from, day_to=day_to, mac_name=mac_name)
    ), "tms-stophistory.csv")


# ---------------------------------------------------------------- showstyle --

@router.get("/showstyle")
def showstyle(
    db: Session = Depends(get_db),
    data: str = HistoryData,
    sel_mode: str = Sel(),
    loom: list[str] = Query(default=None),
    style: list[str] = Query(default=None),
    mac_name: str | None = None,
    day_from: str | None = None,
    day_to: str | None = None,
) -> dict:
    records = history.load_showstyle_records(
        db, source=data, day_from=day_from, day_to=day_to, mac_name=mac_name
    )
    return _screen_out(screens.showstyle_screen(
        records, data=data, sel_mode=sel_mode, loom=loom or (), style=style or ())
    )


@router.get("/showstyle.csv")
def showstyle_csv(
    db: Session = Depends(get_db),
    data: str = HistoryData,
    sel_mode: str = Sel(),
    loom: list[str] = Query(default=None),
    style: list[str] = Query(default=None),
    mac_name: str | None = None,
    day_from: str | None = None,
    day_to: str | None = None,
) -> Response:
    records = history.load_showstyle_records(
        db, source=data, day_from=day_from, day_to=day_to, mac_name=mac_name
    )
    return _csv_response(screens.showstyle_screen(
        records, data=data, sel_mode=sel_mode, loom=loom or (), style=style or ()),
        "tms-showstyle.csv")
