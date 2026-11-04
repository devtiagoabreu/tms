"""Coleta continua do status ao vivo dos teares.

Alimenta ``live_status``, que é a base do detalhamento de paradas por causa no
dashboard diário — inclusive em dias em que ninguém abriu o monitor. A coleta
roda em paralelo (rede) e grava uma linha por tear e por ciclo.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import select
from sqlalchemy.orm import Session

from tms.collector import fetch_live
from tms.live_store import persist_live
from tms.models.masters import Machine

log = logging.getLogger(__name__)


def collect_live_once(
    db: Session,
    *,
    timeout: float = 10.0,
    max_workers: int = 8,
) -> int:
    """Lê todos os teares ativos com IP e persiste em ``live_status``.

    Devolve quantas amostras foram gravadas. Erros de comunicação não levantam:
    são persistidos como amostras com ``error`` (igual ao coletor do legado).
    """
    machines = list(
        db.execute(
            select(Machine)
            .where(Machine.active.is_(True))
            .where(Machine.ip_addr.is_not(None))
        ).scalars()
    )
    if not machines:
        return 0

    def work(machine: Machine):
        return machine.mac_name, fetch_live(machine.ip_addr, timeout=timeout)

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        results = dict(pool.map(work, machines))

    ids = {machine.mac_name: machine.id for machine in machines}
    count = persist_live(db, ids, results)
    db.commit()

    errors = sum(1 for live in results.values() if live.error is not None)
    if errors:
        log.info("Coleta ao vivo: %s amostras (%s com erro)", count, errors)
    return count
