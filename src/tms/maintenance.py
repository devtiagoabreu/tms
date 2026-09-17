"""Retenção e reprocessamento dos dados ingeridos.

- ``purge``: apaga linhas por intervalo de dias em tabelas selecionadas.
- ``rebuild-agg``: recalcula `agg_shift` a partir de `daily_raw`.

Uso::

    python -m tms.maintenance purge --to 2024.12.31 --sources stop_events,daily_raw
    python -m tms.maintenance rebuild-agg --from 2025.01.01 --to 2025.12.31
"""

from __future__ import annotations

import argparse
from typing import Callable, Dict, Iterable, Optional, Sequence

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from tms.ingest.pipeline import rebuild_agg
from tms.models.runtime import (
    AggShift,
    DailyRaw,
    MachineSnapshot,
    OperatorDaily,
    StopEvent,
)

PURGE_SOURCES = ("daily_raw", "agg_shift", "stop_events", "operator_daily", "machine_snapshots")

# fonte → (modelo, coluna de data, coluna usada como limite superior)
_PURGE_TABLE = {
    "daily_raw": (DailyRaw, "day"),
    "agg_shift": (AggShift, "shift_id"),
    "stop_events": (StopEvent, "day"),
    "operator_daily": (OperatorDaily, "day"),
    "machine_snapshots": (MachineSnapshot, "shift_id"),
}


def purge(
    db: Session,
    *,
    day_from: Optional[str] = None,
    day_to: Optional[str] = None,
    sources: Iterable[str] = PURGE_SOURCES,
    dry_run: bool = False,
) -> Dict[str, int]:
    """Apaga (ou conta, em dry-run) linhas no intervalo ``[day_from, day_to]``."""
    if not day_from and not day_to:
        raise ValueError("informe ao menos day_from ou day_to (evita apagar tudo)")

    counts: Dict[str, int] = {}
    for source in sources:
        if source not in _PURGE_TABLE:
            raise ValueError(f"fonte inválida: {source}")
        model, col_name = _PURGE_TABLE[source]
        column = getattr(model, col_name)
        conds = []
        if day_from:
            conds.append(column >= day_from)
        if day_to:
            upper = f"{day_to}.9" if col_name == "shift_id" else day_to
            conds.append(column <= upper)
        if dry_run:
            counts[source] = int(
                db.execute(select(func.count()).select_from(model).where(*conds)).scalar_one()
            )
        else:
            counts[source] = int(db.execute(delete(model).where(*conds)).rowcount or 0)
    if not dry_run:
        db.commit()
    return counts


def _cmd_purge(db: Session, args: argparse.Namespace) -> int:
    sources = args.sources.split(",") if args.sources else PURGE_SOURCES
    counts = purge(
        db,
        day_from=args.date_from,
        day_to=args.date_to,
        sources=sources,
        dry_run=args.dry_run,
    )
    tag = "seriam apagadas" if args.dry_run else "apagadas"
    print(f"[purge] linhas {tag}:")
    for source in sources:
        print(f"  {source:20}: {counts.get(source, 0)}")
    return 0


def _cmd_rebuild(db: Session, args: argparse.Namespace) -> int:
    stats = rebuild_agg(db, day_from=args.date_from, day_to=args.date_to, mac_name=args.mac_name)
    db.commit()
    print(f"[rebuild-agg] agg_shift recalculadas: {stats.agg_shift}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tms.maintenance", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_purge = sub.add_parser("purge", help="apaga linhas por intervalo de dias")
    p_purge.add_argument("--from", dest="date_from", help="data inicial YYYY.MM.DD (inclusive)")
    p_purge.add_argument("--to", dest="date_to", help="data final YYYY.MM.DD (inclusive)")
    p_purge.add_argument("--sources", help=f"lista separada por vírgula (default: {','.join(PURGE_SOURCES)})")
    p_purge.add_argument("--dry-run", action="store_true", help="apenas conta, não apaga")
    p_purge.set_defaults(func=_cmd_purge)

    p_rebuild = sub.add_parser("rebuild-agg", help="recalcula agg_shift a partir de daily_raw")
    p_rebuild.add_argument("--from", dest="date_from", help="data inicial YYYY.MM.DD (inclusive)")
    p_rebuild.add_argument("--to", dest="date_to", help="data final YYYY.MM.DD (inclusive)")
    p_rebuild.add_argument("--mac-name", dest="mac_name", help="restringe a um tear")
    p_rebuild.set_defaults(func=_cmd_rebuild)
    return parser


def main(argv: Optional[Sequence[str]] = None, session_factory: Optional[Callable[[], Session]] = None) -> int:
    args = build_parser().parse_args(argv)
    if session_factory is None:
        from tms.db.base import SessionLocal

        session_factory = SessionLocal
    db = session_factory()
    try:
        return args.func(db, args)
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
