"""Coleta ao vivo do estado dos teares.

Busca o payload ``ext.cgi?func=get_stat`` de cada tear (protocolo do legado
`loom/apistate.cgi::get_jat710_loom_status`) e devolve :class:`LiveStatus`.
Usa apenas a stdlib (`urllib`) para não adicionar dependências de runtime.
"""

from __future__ import annotations

import argparse
import json
import socket
import sys
import urllib.error
import urllib.request
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from tms.core import live as live_mod
from tms.core.live import LiveStatus, parse_live
from tms.core.state import label as state_label
from tms.core.live import live_to_monitor_state

LIVE_PATH = "/cgi-bin/ext.cgi?func=get_stat"
DEFAULT_TIMEOUT = 5.0

_NOT_SUPPORTED_PREFIXES = ("Not supported.", "func(command) not found.")


def _decode(data: bytes) -> str:
    for encoding in ("shift_jis", "utf-8", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def fetch_live(
    host: str,
    *,
    scheme: str = "http",
    path: str = LIVE_PATH,
    timeout: float = DEFAULT_TIMEOUT,
) -> LiveStatus:
    """Coleta o estado de um tear; nunca levanta — retorna o erro em `LiveStatus`."""
    if host.startswith("http://") or host.startswith("https://"):
        url = host.rstrip("/") + path
    else:
        url = f"{scheme}://{host}{path}"

    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            body = _decode(response.read())
    except urllib.error.HTTPError as exc:
        code = live_mod.HTTP_NOT_FOUND if exc.code == 404 else live_mod.HTTP_ERROR
        return live_mod.error_status(code)
    except (socket.timeout, TimeoutError):
        return live_mod.error_status(live_mod.PING_TIMEOUT)
    except urllib.error.URLError as exc:
        reason = exc.reason
        if isinstance(reason, (socket.timeout, TimeoutError)):
            return live_mod.error_status(live_mod.PING_TIMEOUT)
        return live_mod.error_status(live_mod.PING_ERROR)
    except OSError:
        return live_mod.error_status(live_mod.SOCKET_ERROR)

    lines = body.splitlines()
    if not lines or lines[0].startswith(_NOT_SUPPORTED_PREFIXES) or len(lines) == 20:
        return live_mod.error_status(live_mod.NOT_SUPPORT)
    return parse_live(lines)


def collect(
    machines: Iterable[Tuple[str, str]],
    *,
    scheme: str = "http",
    path: str = LIVE_PATH,
    timeout: float = DEFAULT_TIMEOUT,
) -> Dict[str, LiveStatus]:
    """Coleta sequencialmente; `machines` é uma sequência de ``(nome, host)``."""
    return {
        name: fetch_live(host, scheme=scheme, path=path, timeout=timeout)
        for name, host in machines
    }


def _machines_from_db() -> List[Tuple[str, str]]:
    from sqlalchemy import select

    from tms.db.base import SessionLocal
    from tms.models.masters import Machine

    with SessionLocal() as session:
        rows = session.execute(
            select(Machine.mac_name, Machine.ip_addr).where(Machine.ip_addr.is_not(None))
        ).all()
    return [(name, ip) for name, ip in rows if ip]


def _parse_hosts(values: Optional[Sequence[str]]) -> List[Tuple[str, str]]:
    machines: List[Tuple[str, str]] = []
    for value in values or ():
        name, sep, host = value.partition("=")
        machines.append((name, host) if sep else (value, value))
    return machines


def _describe(name: str, live: LiveStatus, lang: str) -> dict:
    state = live_to_monitor_state(live)
    return {
        "mac_name": name,
        "mac_type": live.mac_type,
        "state": state,
        "state_label": state_label(state, lang),
        "status": live.status,
        "duration": live.duration,
        "rpm": live.value("rpm"),
        "efficiency": live.effic_shift,
        "error": live.error,
        "complete": live.complete,
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Coleta o estado ao vivo dos teares.")
    parser.add_argument("--host", action="append", metavar="NOME=IP", help="tear (repetível)")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument("--path", default=LIVE_PATH)
    parser.add_argument("--scheme", default="http")
    parser.add_argument("--lang", default="pt")
    parser.add_argument("--json", action="store_true", help="saída JSON (default)")
    args = parser.parse_args(argv)

    machines = _parse_hosts(args.host)
    if not machines:
        machines = _machines_from_db()
    if not machines:
        print("Nenhum tear com IP configurado.", file=sys.stderr)
        return 1

    result = collect(machines, scheme=args.scheme, path=args.path, timeout=args.timeout)
    payload = [_describe(name, live, args.lang) for name, live in result.items()]
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
