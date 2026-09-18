"""Retenção e reprocessamento dos dados ingeridos.

- ``retention``: aplica a política em camadas (1/3/12 meses).
- ``purge``: apaga linhas por intervalo de dias em tabelas selecionadas.
- ``rebuild-agg``: recalcula `agg_shift` a partir de `daily_raw`.

Uso::

    python -m tms.maintenance retention --dry-run
    python -m tms.maintenance purge --to 2024.12.31 --sources stop_events,daily_raw
    python -m tms.maintenance rebuild-agg --from 2025.01.01 --to 2025.12.31
"""

from __future__ import annotations

import argparse
from datetime import date
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

# Política de retenção em camadas (meses atrás do registro mais novo), espelhando
# `old_03/06/12_ym` do TMSDATAfinal.pm e o merge do legado:
#   snapshot (`current`) = 1 mês; bruto (`shift`/`stop_history`) = 3 meses;
#   agregado (`agg_shift`/`operator_daily`, base de semana/mês) = 12 meses.
RETENTION_MONTHS = {"snapshot": 1, "raw": 2, "agg": 11}

# (nome, camada, modelo, coluna de data)
_RETENTION_SPECS = (
    ("machine_snapshots", "snapshot", MachineSnapshot, "shift_id"),
    ("daily_raw", "raw", DailyRaw, "day"),
    ("stop_events", "raw", StopEvent, "day"),
    ("operator_daily", "agg", OperatorDaily, "day"),
    ("agg_shift", "agg", AggShift, "shift_id"),
)

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


def months_ago(day: str, months: int) -> str:
    """``YYYY.MM.DD`` recuado em ``months`` → ``YYYY.MM`` (aritmética do legado)."""
    year, month = int(day[:4]), int(day[5:7])
    total = year * 12 + (month - 1) - months
    new_year, new_month = divmod(total, 12)
    return f"{new_year:04d}.{new_month + 1:02d}"


def _newest_day(db: Session) -> Optional[str]:
    """Data mais recente entre as tabelas (âncora da retenção)."""
    candidates = [
        db.execute(select(func.max(DailyRaw.day))).scalar_one(),
        db.execute(select(func.max(StopEvent.day))).scalar_one(),
        db.execute(select(func.max(OperatorDaily.day))).scalar_one(),
    ]
    for value in db.execute(select(func.max(AggShift.shift_id))).scalars():
        if value:
            candidates.append(value[:10])
    for value in db.execute(select(func.max(MachineSnapshot.shift_id))).scalars():
        if value:
            candidates.append(value[:10])
    candidates = [c for c in candidates if c]
    return max(candidates) if candidates else None


def retention(
    db: Session,
    *,
    reference_day: Optional[str] = None,
    months: Optional[Dict[str, int]] = None,
    dry_run: bool = False,
) -> Dict[str, int]:
    """Aplica a retenção em camadas a partir de ``reference_day``.

    Devolve a contagem (apagada, ou apenas contada em dry-run) por tabela.
    """
    if reference_day is None:
        reference_day = _newest_day(db) or date.today().strftime("%Y.%m.%d")
    offsets = dict(RETENTION_MONTHS)
    if months:
        offsets.update(months)

    counts: Dict[str, int] = {}
    for name, tier, model, col_name in _RETENTION_SPECS:
        cutoff = f"{months_ago(reference_day, offsets[tier])}.01"
        column = getattr(model, col_name)
        if dry_run:
            counts[name] = int(
                db.execute(
                    select(func.count()).select_from(model).where(column < cutoff)
                ).scalar_one()
            )
        else:
            counts[name] = int(
                db.execute(delete(model).where(column < cutoff)).rowcount or 0
            )
    if not dry_run:
        db.commit()
    return counts


def _cmd_retention(db: Session, args: argparse.Namespace) -> int:
    months = None
    if args.snapshot_months is not None or args.raw_months is not None or args.agg_months is not None:
        months = dict(RETENTION_MONTHS)
        if args.snapshot_months is not None:
            months["snapshot"] = args.snapshot_months
        if args.raw_months is not None:
            months["raw"] = args.raw_months
        if args.agg_months is not None:
            months["agg"] = args.agg_months
    counts = retention(
        db, reference_day=args.reference, months=months, dry_run=args.dry_run
    )
    tag = "seriam apagadas" if args.dry_run else "apagadas"
    print(f"[retention] referência: {args.reference or 'auto'}; linhas {tag}:")
    for name, count in counts.items():
        print(f"  {name:20}: {count}")
    return 0


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

    p_retention = sub.add_parser(
        "retention", help="aplica a retenção em camadas (1/3/12 meses)"
    )
    p_retention.add_argument(
        "--reference", help="data de referência YYYY.MM.DD (default: mais nova do banco)"
    )
    p_retention.add_argument("--dry-run", action="store_true", help="apenas conta, não apaga")
    p_retention.add_argument(
        "--snapshot-months", type=int, help=f"meses de machine_snapshots (default: {RETENTION_MONTHS['snapshot']})"
    )
    p_retention.add_argument(
        "--raw-months", type=int, help=f"meses de daily_raw/stop_events (default: {RETENTION_MONTHS['raw']})"
    )
    p_retention.add_argument(
        "--agg-months", type=int, help=f"meses de agg_shift/operator_daily (default: {RETENTION_MONTHS['agg']})"
    )
    p_retention.set_defaults(func=_cmd_retention)
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
