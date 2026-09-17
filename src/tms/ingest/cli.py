"""CLI de ingestão: `python -m tms.ingest <diretorio>`.

Exemplos::

    python -m tms.ingest docs/legado/htdocs/tmsdata --dry-run
    python -m tms.ingest docs/legado/htdocs/tmsdata --sources shift,stophistory

A URL do banco vem de `TMS_DATABASE_URL` (ver `tms.core.config`).
"""

from __future__ import annotations

import argparse
import sys
from typing import Callable, Optional, Sequence

from tms.ingest.pipeline import (
    IngestStats,
    SOURCES,
    ingest_directory,
    preview_directory,
)


def _print_stats(stats: IngestStats, title: str) -> None:
    print(title)
    print(f"  arquivos lidos        : {stats.files}")
    print(f"  maquinas (unicas)     : {stats.machines}")
    print(f"  machine_snapshots     : {stats.snapshots}")
    print(f"  shift_schedules       : {stats.shift_schedules}")
    print(f"  daily_raw             : {stats.daily_raw}")
    print(f"  agg_shift             : {stats.agg_shift}")
    print(f"  stop_events           : {stats.stop_events}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m tms.ingest",
        description="Ingere os arquivos legados de um tmsdata/ no PostgreSQL.",
    )
    parser.add_argument("directory", help="raiz do tmsdata (contem current/, shift/, stop_history/)")
    parser.add_argument(
        "--sources",
        default="all",
        help=f"fontes a ingerir, separadas por virgula ({', '.join(SOURCES)} ou 'all')",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="apenas conta o que seria ingerido, sem escrever no banco",
    )
    parser.add_argument("--quiet", action="store_true", help="nao imprime o relatorio")
    return parser


def main(
    argv: Optional[Sequence[str]] = None,
    session_factory: Optional[Callable[[], object]] = None,
) -> int:
    args = build_parser().parse_args(argv)

    if args.dry_run:
        try:
            stats = preview_directory(args.directory, sources=args.sources)
        except (ValueError, FileNotFoundError) as exc:
            print(f"erro: {exc}", file=sys.stderr)
            return 2
        if not args.quiet:
            _print_stats(stats, f"[dry-run] {args.directory}")
        return 0

    if session_factory is None:
        from tms.db.base import SessionLocal as session_factory  # noqa: N813

    db = session_factory()
    try:
        stats = ingest_directory(db, args.directory, sources=args.sources)
    except ValueError as exc:
        db.rollback()
        print(f"erro: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        print(f"erro ao ingerir: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()

    if not args.quiet:
        _print_stats(stats, f"[ok] {args.directory}")
    return 0
