"""Endpoints do dashboard de coleta diaria."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional

from datetime import date, datetime
from io import StringIO
import csv

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tms.app.deps.auth import require_roles
from tms.db.base import get_db
from tms.models.auth import UserRole
from tms.models.daily import DailyCollectionItem, DailyCollectionRun, DailyLoomData
from tms.models.masters import Machine
from tms.services import collection_progress

def _aplica_multiplo(valor: float | None, is_double: bool) -> float | None:
    """Aplica multiplicador de tear duplo (x2) se aplicável."""
    if valor is None:
        return None
    return round(float(valor) * (2.0 if is_double else 1.0), 3)
from tms.services.daily_collection import (
    backfill,
    collect_daily_data,
    collection_gaps,
    get_yesterday,
    retry_pending,
)

router = APIRouter(prefix="/api/daily", tags=["daily"])


def _iso(value) -> Optional[str]:
    return value.isoformat() if value else None


def _item_out(item: DailyCollectionItem) -> dict:
    return {
        "mac_name": item.mac_name,
        "mac_type": item.mac_type,
        "ip_addr": item.ip_addr,
        "status": item.status,
        "attempts": item.attempts,
        "error": item.error_reason,
        "collected_at": _iso(item.collected_at),
        "in_retry_queue": item.in_retry_queue,
        "last_retry_at": _iso(item.last_retry_at),
    }


def _run_out(run: DailyCollectionRun, items: list[DailyCollectionItem]) -> dict:
    return {
        "collection_date": run.collection_date.isoformat(),
        "status": run.status,
        "started_at": _iso(run.started_at),
        "finished_at": _iso(run.finished_at),
        "total_machines": run.total_machines,
        "success_count": run.success_count,
        "failed_count": run.failed_count,
        "retry_count": run.retry_count,
        "items": [_item_out(i) for i in items],
    }


def _items_of(db: Session, run_id: int) -> list[DailyCollectionItem]:
    return list(
        db.execute(
            select(DailyCollectionItem)
            .where(DailyCollectionItem.run_id == run_id)
            .order_by(DailyCollectionItem.mac_name)
        ).scalars()
    )


def _summary(run: DailyCollectionRun, rows: list, items: list[DailyCollectionItem]) -> dict:
    # rows podem ser DailyLoomData puro ou tupla (DailyLoomData, is_double) vinda de JOIN
    loom_rows = [r.DailyLoomData if hasattr(r, "DailyLoomData") else r for r in rows]

    efficiencies = [r.efficiency for r in loom_rows if r.efficiency is not None]
    rpms = [r.rpm for r in loom_rows if r.rpm is not None]
    production = [r.production for r in loom_rows if r.production is not None]

    def total(attr: str):
        values = [getattr(r, attr) for r in loom_rows if getattr(r, attr) is not None]
        return round(sum(values), 1) if values else None

    return {
        "looms_collected": len(loom_rows),
        "looms_missing": sum(1 for i in items if i.status != "success"),
        "avg_efficiency": round(sum(efficiencies) / len(efficiencies), 2) if efficiencies else None,
        "avg_rpm": round(sum(rpms) / len(rpms), 2) if rpms else None,
        "total_production": round(sum(production), 2) if production else None,
        "total_stops": total("total_stop_ct") or 0,
        "breakdown_known": any(
            r.trama_stops is not None or r.urdume_stops is not None or r.outros_stops is not None
            for r in loom_rows
        ),
        "trama_stops": total("trama_stops"),
        "urdume_stops": total("urdume_stops"),
        "outros_stops": total("outros_stops"),
        "trama_stops_min": total("trama_stops_min"),
        "urdume_stops_min": total("urdume_stops_min"),
        "outros_stops_min": total("outros_stops_min"),
    }


@router.get("")
def daily_status(
    day: Optional[date] = Query(None, description="Data coletada (default: dia anterior)"),
    db: Session = Depends(get_db),
) -> dict:
    """Situacao da coleta diaria: resumo, teares coletados e teares que faltaram."""
    target = day or get_yesterday()
    run = db.execute(
        select(DailyCollectionRun).where(DailyCollectionRun.collection_date == target)
    ).scalar_one_or_none()

    if run is None:
        return {
            "collection_date": target.isoformat(),
            "status": "not_started",
            "total_machines": 0,
            "success_count": 0,
            "failed_count": 0,
            "retry_count": 0,
            "summary": None,
            "items": [],
            "looms": [],
        }

    items = _items_of(db, run.id)
    # JOIN com machines para saber se o tear é duplo (is_double)
    rows = list(
        db.execute(
            select(DailyLoomData, Machine.is_double)
            .outerjoin(Machine, Machine.mac_name == DailyLoomData.mac_name)
            .where(DailyLoomData.collection_date == target)
            .order_by(DailyLoomData.mac_name)
        ).all()
    )
    payload = _run_out(run, items)
    payload["summary"] = _summary(run, rows, items)
    payload["looms"] = [
        {
            "mac_name": r.DailyLoomData.mac_name,
            "source": r.DailyLoomData.source,
            "shift_id": r.DailyLoomData.shift_id,
            "style": r.DailyLoomData.style,
            "production": r.DailyLoomData.production,
            "picks": r.DailyLoomData.picks,
            "pontos_reais": _aplica_multiplo(r.DailyLoomData.pontos_reais, bool(r.is_double) if r.is_double is not None else False)
            if r.DailyLoomData.pontos_reais is not None
            else (_aplica_multiplo(r.DailyLoomData.picks * 10, bool(r.is_double) if r.is_double is not None else False)
                  if r.DailyLoomData.picks is not None else None),
            "efficiency": r.DailyLoomData.efficiency,
            "rpm": r.DailyLoomData.rpm,
            "run_time_min": r.DailyLoomData.run_time_min,
            "stop_time_min": r.DailyLoomData.stop_time_min,
            "total_stop_ct": r.DailyLoomData.total_stop_ct,
            "total_stop_tm_min": r.DailyLoomData.total_stop_tm_min,
            "trama_stops": r.DailyLoomData.trama_stops,
            "trama_stops_min": r.DailyLoomData.trama_stops_min,
            "urdume_stops": r.DailyLoomData.urdume_stops,
            "urdume_stops_min": r.DailyLoomData.urdume_stops_min,
            "outros_stops": r.DailyLoomData.outros_stops,
            "outros_stops_min": r.DailyLoomData.outros_stops_min,
            "collected_at": _iso(r.DailyLoomData.collected_at),
            "is_double": bool(r.is_double) if r.is_double is not None else False,
        }
        for r in rows
    ]
    return payload


@router.get("/history")
def daily_history(limit: int = Query(30, ge=1, le=365), db: Session = Depends(get_db)) -> list[dict]:
    """Ultimas execucoes da coleta diaria."""
    runs = list(
        db.execute(
            select(DailyCollectionRun)
            .order_by(DailyCollectionRun.collection_date.desc())
            .limit(limit)
        ).scalars()
    )
    return [
        {
            "collection_date": r.collection_date.isoformat(),
            "status": r.status,
            "total_machines": r.total_machines,
            "success_count": r.success_count,
            "failed_count": r.failed_count,
            "retry_count": r.retry_count,
            "finished_at": _iso(r.finished_at),
        }
        for r in runs
    ]


@router.post("/collect")
def daily_collect(
    day: Optional[date] = Query(None, description="Data a coletar (default: dia anterior)"),
    force: bool = Query(False, description="Refaz a coleta mesmo se ja concluida"),
    db: Session = Depends(get_db),
    _=Depends(require_roles(UserRole.admin)),
) -> dict:
    """Dispara a coleta do dia anterior (bloqueado se ja executada no dia)."""
    target = day or get_yesterday()
    run = collect_daily_data(db, target, force=force)
    items = _items_of(db, run.id)
    return _run_out(run, items)


@router.get("/progress")
def daily_progress(
    day: Optional[date] = Query(None, description="Data coletada (default: dia anterior)"),
) -> dict:
    """Andamento em tempo real da coleta (usado pela barra do dashboard)."""
    return collection_progress.snapshot(day or get_yesterday())


@router.get("/gaps")
def daily_gaps(
    days: int = Query(7, ge=1, le=60, description="Tamanho da janela em dias"),
    db: Session = Depends(get_db),
) -> dict:
    """Lacunas de coleta: dias sem execucao e teares que ficaram sem coleta."""
    return collection_gaps(db, days=days)


@router.post("/backfill")
def daily_backfill(
    start: Optional[date] = Query(None, description="Primeiro dia (default: 7 dias atras)"),
    end: Optional[date] = Query(None, description="Ultimo dia (default: ontem)"),
    db: Session = Depends(get_db),
    _=Depends(require_roles(UserRole.admin)),
) -> dict:
    """Preenche lacunas de dias passados usando apenas fontes historicas."""
    last = get_yesterday()
    final = min(end or last, last)
    first = start or (final - timedelta(days=6))
    if first > final:
        raise HTTPException(status_code=422, detail="Data inicial posterior a final")
    if (final - first).days > 90:
        raise HTTPException(status_code=422, detail="Intervalo maximo de 90 dias")

    runs = backfill(db, first, final)
    return {
        "start": first.isoformat(),
        "end": final.isoformat(),
        "runs": [
            {
                "collection_date": run.collection_date.isoformat(),
                "status": run.status,
                "success_count": run.success_count,
                "failed_count": run.failed_count,
                "retry_count": run.retry_count,
            }
            for run in runs
        ],
    }


@router.post("/retry")
def daily_retry(
    day: Optional[date] = Query(None, description="Data da coleta (default: dia anterior)"),
    db: Session = Depends(get_db),
    _=Depends(require_roles(UserRole.admin)),
) -> dict:
    """Reprocessa a fila de teares que faltaram."""
    target = day or get_yesterday()
    run = retry_pending(db, target, respect_interval=False)
    if run is None:
        raise HTTPException(status_code=404, detail="Nenhuma coleta encontrada para a data")
    items = _items_of(db, run.id)
    return _run_out(run, items)


# ---------------------------------------------------------------------------
# Relatórios agregados da coleta diária (daily_loom_data)
# ---------------------------------------------------------------------------

_REPORT_VIEWS = {"day", "loom", "style"}


def _date_range(
    day_from: Optional[str], day_to: Optional[str]
) -> tuple[Optional[date], Optional[date]]:
    """Converte strings YYYY-MM-DD para date."""
    f: Optional[date] = None
    t: Optional[date] = None
    if day_from:
        try:
            f = datetime.strptime(day_from, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="day_from inválido (use YYYY-MM-DD)")
    if day_to:
        try:
            t = datetime.strptime(day_to, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="day_to inválido (use YYYY-MM-DD)")
    return f, t


def _report_query(
    db: Session,
    view: str,
    day_from: Optional[date],
    day_to: Optional[date],
    mac_name: Optional[str],
    style: Optional[str],
):
    """Constrói a query agregada conforme a visão escolhida."""
    if view not in _REPORT_VIEWS:
        raise HTTPException(status_code=400, detail="view inválida (day, loom ou style)")

    base = select(DailyLoomData)
    if day_from is not None:
        base = base.where(DailyLoomData.collection_date >= day_from)
    if day_to is not None:
        base = base.where(DailyLoomData.collection_date <= day_to)
    if mac_name:
        base = base.where(DailyLoomData.mac_name.ilike(f"%{mac_name}%"))
    if style:
        base = base.where(DailyLoomData.style.ilike(f"%{style}%"))

    stop_avg = (
        func.sum(DailyLoomData.total_stop_tm_min)
        / func.nullif(func.sum(DailyLoomData.total_stop_ct), 0)
    ).label("avg_stop_tm")

    if view == "day":
        group_col = DailyLoomData.collection_date
        key_label = DailyLoomData.collection_date.label("key")
        stmt = (
            select(
                group_col,
                key_label,
                func.count(DailyLoomData.id).label("n_rows"),
                func.sum(DailyLoomData.meters).label("meters"),
                func.sum(DailyLoomData.picks).label("picks"),
                func.sum(DailyLoomData.pontos_reais).label("pontos_reais"),
                func.sum(DailyLoomData.metros_reais).label("metros_reais"),
                func.avg(DailyLoomData.efficiency).label("avg_efficiency"),
                func.avg(DailyLoomData.rpm).label("avg_rpm"),
                func.sum(DailyLoomData.total_stop_ct).label("total_stops"),
                stop_avg,
            )
        )
    elif view == "loom":
        group_col = DailyLoomData.mac_name
        key_label = DailyLoomData.mac_name.label("key")
        is_double = Machine.is_double.label("is_double")
        stmt = (
            select(
                group_col,
                key_label,
                is_double,
                func.count(DailyLoomData.id).label("n_rows"),
                func.sum(DailyLoomData.meters).label("meters"),
                func.sum(DailyLoomData.picks).label("picks"),
                func.sum(DailyLoomData.pontos_reais).label("pontos_reais"),
                func.sum(DailyLoomData.metros_reais).label("metros_reais"),
                func.avg(DailyLoomData.efficiency).label("avg_efficiency"),
                func.avg(DailyLoomData.rpm).label("avg_rpm"),
                func.sum(DailyLoomData.total_stop_ct).label("total_stops"),
            )
            .join(Machine, Machine.mac_name == DailyLoomData.mac_name)
        )
    else:  # style
        group_col = DailyLoomData.style
        key_label = DailyLoomData.style.label("key")
        stmt = (
            select(
                group_col,
                key_label,
                func.count(DailyLoomData.id).label("n_rows"),
                func.sum(DailyLoomData.meters).label("meters"),
                func.sum(DailyLoomData.picks).label("picks"),
                func.sum(DailyLoomData.pontos_reais).label("pontos_reais"),
                func.sum(DailyLoomData.metros_reais).label("metros_reais"),
                func.avg(DailyLoomData.efficiency).label("avg_efficiency"),
                func.avg(DailyLoomData.rpm).label("avg_rpm"),
                func.sum(DailyLoomData.total_stop_ct).label("total_stops"),
                stop_avg,
            )
        )

    # Aplica filtros comuns (date range, mac_name, style)
    if day_from is not None:
        stmt = stmt.where(DailyLoomData.collection_date >= day_from)
    if day_to is not None:
        stmt = stmt.where(DailyLoomData.collection_date <= day_to)
    if mac_name:
        stmt = stmt.where(DailyLoomData.mac_name.ilike(f"%{mac_name}%"))
    if style:
        stmt = stmt.where(DailyLoomData.style.ilike(f"%{style}%"))

    stmt = stmt.group_by(group_col).order_by(group_col)
    if view == "loom":
        stmt = stmt.group_by(is_double)

    rows = list(db.execute(stmt))
    return rows, view


def _report_rows(
    db: Session,
    view: str,
    day_from: Optional[str],
    day_to: Optional[str],
    mac_name: Optional[str],
    style: Optional[str],
):
    f, t = _date_range(day_from, day_to)
    rows, view = _report_query(db, view, f, t, mac_name, style)
    out = []
    for r in rows:
        is_double = bool(getattr(r, "is_double", False)) if hasattr(r, "is_double") else False
        multiplicador = 2.0 if is_double else 1.0

        picks_val = round(float(r.picks), 1) if r.picks is not None else None
        meters_val = round(float(r.meters), 1) if r.meters is not None else None

        # pontos_reais: usa valor já armazenado no banco (com multiplicador do tear duplo)
        # se não existir, calcula a partir de picks * 10 * multiplicador
        pontos_reais_raw = getattr(r, "pontos_reais", None)
        pontos_reais_val = None
        if pontos_reais_raw is not None:
            pontos_reais_val = round(float(pontos_reais_raw), 1)
        elif picks_val is not None:
            pontos_reais_val = round(picks_val * 10 * multiplicador, 1)

        # metros_reais: usa valor já armazenado no banco (com multiplicador do tear duplo)
        # se não existir, calcula a partir de meters * multiplicador
        metros_reais_raw = getattr(r, "metros_reais", None)
        metros_reais_val = None
        if metros_reais_raw is not None:
            metros_reais_val = round(float(metros_reais_raw), 1)
        elif meters_val is not None:
            metros_reais_val = round(meters_val * multiplicador, 1)

        avg_efficiency_raw = getattr(r, "avg_efficiency", None)
        avg_rpm_raw = getattr(r, "avg_rpm", None)
        total_stops_raw = getattr(r, "total_stops", None)
        avg_stop_tm_raw = getattr(r, "avg_stop_tm", None)

        out.append(
            {
                "key": r.key.isoformat() if hasattr(r.key, "isoformat") else r.key,
                "n_rows": r.n_rows,
                "meters": meters_val,
                "picks": picks_val,
                "pontos_reais": pontos_reais_val,
                "metros_reais": metros_reais_val,
                "avg_efficiency": round(float(avg_efficiency_raw), 1)
                if avg_efficiency_raw is not None
                else None,
                "avg_rpm": round(float(avg_rpm_raw), 1) if avg_rpm_raw is not None else None,
                "total_stops": int(total_stops_raw) if total_stops_raw is not None else 0,
                "avg_stop_tm": round(float(avg_stop_tm_raw), 2)
                if avg_stop_tm_raw is not None
                else None,
            }
        )
    return out


@router.get("/report")
def daily_report(
    view: str = Query("day", description="day | loom | style"),
    day_from: Optional[str] = Query(None, description="Data inicial (YYYY-MM-DD)"),
    day_to: Optional[str] = Query(None, description="Data final (YYYY-MM-DD)"),
    mac_name: Optional[str] = Query(None, description="Filtrar por tear"),
    style: Optional[str] = Query(None, description="Filtrar por artigo"),
    db: Session = Depends(get_db),
) -> dict:
    """Dados agregados da coleta diária para relatórios (tabela/export)."""
    return {
        "view": view,
        "day_from": day_from,
        "day_to": day_to,
        "rows": _report_rows(db, view, day_from, day_to, mac_name, style),
    }


@router.get("/report/csv")
def daily_report_csv(
    view: str = Query("day", description="day | loom | style"),
    day_from: Optional[str] = Query(None, description="Data inicial (YYYY-MM-DD)"),
    day_to: Optional[str] = Query(None, description="Data final (YYYY-MM-DD)"),
    mac_name: Optional[str] = Query(None, description="Filtrar por tear"),
    style: Optional[str] = Query(None, description="Filtrar por artigo"),
    db: Session = Depends(get_db),
) -> Response:
    """Exporta o relatório agregado em CSV."""
    rows = _report_rows(db, view, day_from, day_to, mac_name, style)

    buf = StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "Chave",
            "Registros",
            "Metros",
            "Metros Reais",
            "Pontos Reais",
            "Media Eficiencia",
            "Media RPM",
            "Qtd Paradas",
            "Tempo Medio Parada (min)",
        ]
    )
    for r in rows:
        writer.writerow(
            [
                r["key"],
                r["n_rows"],
                r["meters"] if r["meters"] is not None else "",
                r["metros_reais"] if r["metros_reais"] is not None else "",
                r["pontos_reais"] if r["pontos_reais"] is not None else "",
                r["avg_efficiency"] if r["avg_efficiency"] is not None else "",
                r["avg_rpm"] if r["avg_rpm"] is not None else "",
                r["total_stops"],
                r["avg_stop_tm"] if r["avg_stop_tm"] is not None else "",
            ]
        )

    filename = f"tms-relatorio-{view}.csv"
    return Response(
        content=buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/report/pdf", response_class=HTMLResponse)
def daily_report_pdf(
    request: Request,
    view: str = Query("day", description="day | loom | style"),
    day_from: Optional[str] = Query(None, description="Data inicial (YYYY-MM-DD)"),
    day_to: Optional[str] = Query(None, description="Data final (YYYY-MM-DD)"),
    mac_name: Optional[str] = Query(None, description="Filtrar por tear"),
    style: Optional[str] = Query(None, description="Filtrar por artigo"),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Retorna HTML pronto para impressão (salvar como PDF via Ctrl+P)."""
    rows = _report_rows(db, view, day_from, day_to, mac_name, style)

    title_map = {"day": "Por Dia", "loom": "Por Tear", "style": "Por Artigo"}
    view_title = title_map.get(view, view)

    total_metros_reais = sum((r["metros_reais"] or 0) for r in rows)
    total_pontos_reais = sum((r["pontos_reais"] or 0) for r in rows)
    total_stops = sum((r["total_stops"] or 0) for r in rows)

    html = f"""<!doctype html>
<html lang="pt-br">
<head>
<meta charset="utf-8">
<title>TMS - Relatório {view_title}</title>
<style>
  @page {{ size: A4; margin: 12mm; }}
  body {{ font-family: Arial, Helvetica, sans-serif; font-size: 8.5pt; color: #111; }}
  h1 {{ font-size: 14pt; margin: 0 0 4px 0; }}
  .sub {{ font-size: 8pt; color: #555; margin: 0 0 12px 0; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ border: 1px solid #999; padding: 3px 5px; text-align: left; }}
  th {{ background: #e8e8e8; font-size: 7.5pt; }}
  td.num {{ text-align: right; }}
  td.center {{ text-align: center; }}
  .foot {{ margin-top: 12px; font-size: 7.5pt; color: #555; border-top: 1px solid #999; padding-top: 6px; }}
  .nodata {{ font-size: 8pt; color: #888; }}
</style>
</head>
<body>
<h1>TMS — Relatório de Coleta Diária ({view_title})</h1>
<p class="sub">
  Período: {_esc_html(day_from or '—')} a {_esc_html(day_to or '—')}
  {f" · Tear: {_esc_html(mac_name)}" if mac_name else ""}
  {f" · Artigo: {_esc_html(style)}" if style else ""}
  · Gerado em {datetime.now().strftime('%d/%m/%Y %H:%M')}
</p>
<table>
  <thead>
    <tr>
      <th style="width:22%">Chave</th>
      <th class="center" style="width:10%">Registros</th>
      <th class="num" style="width:12%">Metros Reais</th>
      <th class="num" style="width:12%">Pontos Reais</th>
      <th class="num" style="width:12%">Média Eficiência</th>
      <th class="num" style="width:10%">Média RPM</th>
      <th class="num" style="width:12%">Qtd Paradas</th>
      <th class="num" style="width:16%">Tempo Médio Parada (min)</th>
    </tr>
  </thead>
  <tbody>
    {"".join(_pdf_row(r) for r in rows) if rows else '<tr><td colspan="8" class="nodata">Sem dados no período informado.</td></tr>'}
  </tbody>
  <tfoot>
    <tr>
      <th>Total</th>
      <th class="center">{len(rows)}</th>
      <th class="num">{total_metros_reais:,.1f}</th>
      <th class="num">{total_pontos_reais:,.1f}</th>
      <th class="num">—</th>
      <th class="num">—</th>
      <th class="num">{total_stops:,}</th>
      <th class="num">—</th>
    </tr>
  </tfoot>
</table>
<p class="foot">TMS — Toyota Loom Monitoring System · Relatório gerado pelo sistema.</p>
<script>window.print();</script>
</body>
</html>"""
    return HTMLResponse(content=html)


def _pdf_row(r: dict) -> str:
    def n(v, d=1):
        if v is None:
            return "-"
        return f"{float(v):,.{d}f}"
    return (
        f"<tr>"
        f"<td>{_esc_html(r['key'])}</td>"
        f"<td class='center'>{r['n_rows']}</td>"
        f"<td class='num'>{n(r['metros_reais'])}</td>"
        f"<td class='num'>{n(r['pontos_reais'])}</td>"
        f"<td class='num'>{n(r['avg_efficiency'])}</td>"
        f"<td class='num'>{n(r['avg_rpm'])}</td>"
        f"<td class='num'>{r['total_stops']:,}</td>"
        f"<td class='num'>{n(r['avg_stop_tm'], 2)}</td>"
        f"</tr>"
    )


def _esc_html(s: Optional[str]) -> str:
    if s is None:
        return ""
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )
