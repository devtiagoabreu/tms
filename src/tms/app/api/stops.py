"""Paradas por tipo (Trama/Urdume/Outros) com quantidade e tempo."""
from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tms.core.stopcodes import CATEGORY_KEYS, CATEGORY_LABELS
from tms.db.base import get_db
from tms.models.masters import Machine
from tms.models.runtime import AggShift

router = APIRouter(prefix="/api", tags=["stops"])


def _latest_agg_by_machine(db: Session) -> Dict[int, AggShift]:
    rn = func.row_number().over(
        partition_by=AggShift.machine_id, order_by=(AggShift.shift_id.desc(), AggShift.id.desc())
    ).label("rn")
    sub = select(AggShift.id, rn).subquery()
    ids = select(sub.c.id).where(sub.c.rn == 1)
    stmt = select(AggShift).where(AggShift.id.in_(ids))
    return {a.machine_id: a for a in db.execute(stmt).scalars()}


@router.get("/stops/summary")
def stops_summary(lang: str = Query("pt"), db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    machines = db.execute(select(Machine).order_by(Machine.mac_name)).scalars().all()
    aggs = _latest_agg_by_machine(db)
    labels = CATEGORY_LABELS.get(lang) or CATEGORY_LABELS.get("pt") or CATEGORY_LABELS["en"]
    result = []
    for m in machines:
        agg = aggs.get(m.id)
        stop_ct = list(agg.stop_ct or []) if agg else []
        stop_tm = list(agg.stop_tm or []) if agg else []
        while len(stop_ct) < len(CATEGORY_KEYS):
            stop_ct.append(0)
        while len(stop_tm) < len(CATEGORY_KEYS):
            stop_tm.append(0.0)
        items = []
        for i, key in enumerate(CATEGORY_KEYS):
            items.append(
                {
                    "key": key,
                    "label": labels.get(key) or key,
                    "count": int(stop_ct[i] or 0),
                    "minutes": float(stop_tm[i] or 0.0),
                }
            )
        trama_ct = items[5]["count"] if len(items) > 5 else 0
        trama_min = items[5]["minutes"] if len(items) > 5 else 0.0
        urdume_ct = (items[0]["count"] if len(items) > 0 else 0) + (
            items[1]["count"] if len(items) > 1 else 0
        )
        urdume_min = (items[0]["minutes"] if len(items) > 0 else 0.0) + (
            items[1]["minutes"] if len(items) > 1 else 0.0
        )
        total_ct = sum(x["count"] for x in items)
        total_min = sum(x["minutes"] for x in items)
        others_ct = max(0, total_ct - trama_ct - urdume_ct)
        others_min = max(0, total_min - trama_min - urdume_min)
        result.append(
            {
                "mac_name": m.mac_name,
                "mac_type": m.mac_type,
                "shift_id": agg.shift_id if agg else None,
                "total_count": total_ct,
                "total_minutes": round(total_min, 1),
                "trama": {
                    "label": labels.get("WEFT_MISS") or "Trama/Weft",
                    "count": trama_ct,
                    "minutes": round(trama_min, 1),
                },
                "urdume": {"label": "Urdume/Warp", "count": urdume_ct, "minutes": round(urdume_min, 1)},
                "outros": {"label": "Outros", "count": others_ct, "minutes": round(others_min, 1)},
                "items": items,
            }
        )
    return result


@router.get("/stops/total")
def stops_total(lang: str = Query("pt"), db: Session = Depends(get_db)) -> Dict[str, Any]:
    machines = db.execute(select(Machine)).scalars().all()
    aggs = _latest_agg_by_machine(db)
    labels = CATEGORY_LABELS.get(lang) or CATEGORY_LABELS.get("pt") or CATEGORY_LABELS["en"]

    stop_ct_total = [0] * len(CATEGORY_KEYS)
    stop_tm_total = [0.0] * len(CATEGORY_KEYS)

    for m in machines:
        agg = aggs.get(m.id)
        if not agg:
            continue
        ct = list(agg.stop_ct or [])
        tm = list(agg.stop_tm or [])
        for i in range(len(CATEGORY_KEYS)):
            if i < len(ct):
                stop_ct_total[i] += int(ct[i] or 0)
            if i < len(tm):
                stop_tm_total[i] += float(tm[i] or 0.0)

    trama_ct = stop_ct_total[5] if len(stop_ct_total) > 5 else 0
    trama_min = stop_tm_total[5] if len(stop_tm_total) > 5 else 0.0
    urdume_ct = (stop_ct_total[0] if len(stop_ct_total) > 0 else 0) + (
        stop_ct_total[1] if len(stop_ct_total) > 1 else 0
    )
    urdume_min = (stop_tm_total[0] if len(stop_tm_total) > 0 else 0.0) + (
        stop_tm_total[1] if len(stop_tm_total) > 1 else 0.0
    )
    total_ct = sum(stop_ct_total)
    total_min = sum(stop_tm_total)
    others_ct = max(0, total_ct - trama_ct - urdume_ct)
    others_min = max(0, total_min - trama_min - urdume_min)

    return {
        "total_count": total_ct,
        "total_minutes": round(total_min, 1),
        "trama": {
            "label": labels.get("WEFT_MISS") or "Trama/Weft",
            "count": trama_ct,
            "minutes": round(trama_min, 1),
        },
        "urdume": {"label": "Urdume/Warp", "count": urdume_ct, "minutes": round(urdume_min, 1)},
        "outros": {"label": "Outros", "count": others_ct, "minutes": round(others_min, 1)},
        "items": [
            {
                "key": key,
                "label": labels.get(key) or key,
                "count": int(stop_ct_total[i] or 0),
                "minutes": round(float(stop_tm_total[i] or 0.0), 1),
            }
            for i, key in enumerate(CATEGORY_KEYS)
        ],
    }
