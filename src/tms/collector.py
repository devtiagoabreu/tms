"""Coleta ao vivo do estado dos teares.

Duas vias do legado:

- **JAT710** (`loom/apistate.cgi::get_jat710_loom_status`): GET
  ``/cgi-bin/ext.cgi?func=get_stat`` no IP do tear;
- **LWT710 via scanner** (`get_scan_loom_status`): POST multipart-like em
  ``/TmsScanner/cgi-bin/mget.cgi`` pedindo ``..\\data\\status\\NNMMM.txt``.

Ambas devolvem o mesmo payload ``Chave=valor`` parseado por :mod:`tms.core.live`.
Usa apenas a stdlib (`urllib`) para não adicionar dependências de runtime.
"""

from __future__ import annotations

import argparse
import json
import re
import socket
import sys
import time
import urllib.error
import urllib.request
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from tms.core import live as live_mod
from tms.core.live import LiveStatus, live_to_monitor_state, parse_live
from tms.core.state import label as state_label

LIVE_PATH = "/cgi-bin/ext.cgi?func=get_stat"
SCAN_PATH = "/TmsScanner/cgi-bin/mget.cgi"
SCAN_BOUNDARY = "----------mget-boundary-strings----------"
DEFAULT_TIMEOUT = 5.0

_NOT_SUPPORTED_PREFIXES = ("Not supported.", "func(command) not found.")

_SCAN_ID = re.compile(r"S([1-5])-([0-9]+)\.([0-9]+)")


def _decode(data: bytes) -> str:
    for encoding in ("shift_jis", "utf-8", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _error_code(exc: BaseException) -> int:
    if isinstance(exc, urllib.error.HTTPError):
        return live_mod.HTTP_NOT_FOUND if exc.code == 404 else live_mod.HTTP_ERROR
    if isinstance(exc, (socket.timeout, TimeoutError)):
        return live_mod.PING_TIMEOUT
    if isinstance(exc, urllib.error.URLError):
        reason = exc.reason
        if isinstance(reason, (socket.timeout, TimeoutError)):
            return live_mod.PING_TIMEOUT
        return live_mod.PING_ERROR
    if isinstance(exc, OSError):
        return live_mod.SOCKET_ERROR
    return live_mod.SYSTEM_ERROR


def _url(host: str, path: str, scheme: str = "http") -> str:
    if host.startswith("http://") or host.startswith("https://"):
        return host.rstrip("/") + path
    return f"{scheme}://{host}{path}"


def fetch_live(
    host: str,
    *,
    scheme: str = "http",
    path: str = LIVE_PATH,
    timeout: float = DEFAULT_TIMEOUT,
) -> LiveStatus:
    """Coleta o estado de um tear; nunca levanta — retorna o erro em `LiveStatus`."""
    try:
        with urllib.request.urlopen(_url(host, path, scheme), timeout=timeout) as response:
            body = _decode(response.read())
    except BaseException as exc:  # noqa: BLE001 - vira status, nunca propaga
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        return live_mod.error_status(_error_code(exc))

    lines = body.splitlines()
    if not lines or lines[0].startswith(_NOT_SUPPORTED_PREFIXES) or len(lines) == 20:
        return live_mod.error_status(live_mod.NOT_SUPPORT)
    return parse_live(lines)


def _scan_filename(mac_id: str) -> Optional[str]:
    match = _SCAN_ID.search(mac_id)
    if not match:
        return None
    return f"{int(match.group(2)):02d}{int(match.group(3)):03d}.txt"


def scan_post_body(mac_ids: Iterable[str]) -> Tuple[str, Dict[str, str]]:
    """Monta o corpo POST do scanner e o mapa arquivo→mac_id (como o legado)."""
    body = f"boundary={SCAN_BOUNDARY}"
    file2mac: Dict[str, str] = {}
    for mac_id in mac_ids:
        filename = _scan_filename(mac_id)
        if filename is None:
            continue
        path = f"..\\data\\status\\{filename}"
        body += f"&file={path}"
        file2mac[path] = mac_id
    return body, file2mac


def parse_mget_response(lines: Sequence[str], file2mac: Dict[str, str]) -> Dict[str, List[str]]:
    """Divide a resposta multipart-like do scanner em blocos por arquivo."""
    groups: Dict[str, List[str]] = {}
    level = 0
    mac_id = ""
    each: List[str] = []
    for line in lines:
        if level == 1:
            if line in file2mac:
                mac_id = file2mac[line]
                level = 2
                each = []
            else:
                level = 0
        elif level == 2:
            if line == SCAN_BOUNDARY:
                if each and each[-1] == "":
                    each.pop()
                groups[mac_id] = each
                level = 1
            else:
                each.append(line)
        elif line == SCAN_BOUNDARY:
            level = 1
    return groups


def fetch_scan_live(
    scan_ip: str,
    mac_ids: Iterable[str],
    *,
    scheme: str = "http",
    path: str = SCAN_PATH,
    timeout: float = DEFAULT_TIMEOUT,
) -> Dict[str, LiveStatus]:
    """Coleta, via scanner, o status de vários teares LWT de uma vez."""
    mac_ids = list(mac_ids)
    body, file2mac = scan_post_body(mac_ids)
    request = urllib.request.Request(
        _url(scan_ip, path, scheme),
        data=body.encode("ascii", errors="replace"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            text = _decode(response.read())
    except BaseException as exc:  # noqa: BLE001 - vira status, nunca propaga
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        code = _error_code(exc)
        return {mac_id: live_mod.error_status(code) for mac_id in mac_ids}

    groups = parse_mget_response(text.splitlines(), file2mac)
    result: Dict[str, LiveStatus] = {}
    for mac_id in mac_ids:
        lines = groups.get(mac_id)
        if not lines:
            result[mac_id] = live_mod.error_status(live_mod.DATA_ERROR)
        elif lines[0].startswith(_NOT_SUPPORTED_PREFIXES) or len(lines) == 20:
            result[mac_id] = live_mod.error_status(live_mod.NOT_SUPPORT)
        else:
            result[mac_id] = parse_live(lines)
    return result


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


def _machines_from_db() -> Tuple[List[Tuple[str, str]], Dict[str, int]]:
    from sqlalchemy import select

    from tms.db.base import SessionLocal
    from tms.models.masters import Machine

    with SessionLocal() as session:
        rows = session.execute(select(Machine)).scalars().all()
    machines = [(m.mac_name, m.ip_addr) for m in rows if m.ip_addr]
    ids = {m.mac_name: m.id for m in rows}
    return machines, ids


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


def _resolve_ids(names: Iterable[str]) -> Dict[str, int]:
    from sqlalchemy import select

    from tms.db.base import SessionLocal
    from tms.models.masters import Machine

    wanted = set(names)
    with SessionLocal() as session:
        rows = session.execute(select(Machine.mac_name, Machine.id)).all()
    return {name: machine_id for name, machine_id in rows if name in wanted}


def _run_once(args: argparse.Namespace) -> int:
    machines = _parse_hosts(args.host)
    ids: Dict[str, int] = {}
    if not machines:
        machines, ids = _machines_from_db()

    result = collect(machines, scheme=args.scheme, path=args.path, timeout=args.timeout)

    if args.scanner_ip and args.scan_id:
        scanned = fetch_scan_live(
            args.scanner_ip, args.scan_id, scheme=args.scheme, timeout=args.timeout
        )
        result.update(scanned)

    if args.persist:
        from tms.db.base import SessionLocal
        from tms.live_store import persist_live

        if not ids:
            ids = _resolve_ids(result)
        with SessionLocal() as session:
            persist_live(session, ids, result)
            session.commit()

    payload = [_describe(name, live, args.lang) for name, live in result.items()]
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Coleta o estado ao vivo dos teares.")
    parser.add_argument("--host", action="append", metavar="NOME=IP", help="tear (repetível)")
    parser.add_argument("--scanner-ip", help="IP do scanner (para teares LWT)")
    parser.add_argument("--scan-id", action="append", help="mac_id do scanner (ex.: S1-1.1)")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument("--path", default=LIVE_PATH)
    parser.add_argument("--scheme", default="http")
    parser.add_argument("--lang", default="pt")
    parser.add_argument("--persist", action="store_true", help="grava em live_status")
    parser.add_argument("--loop", action="store_true", help="coleta continuamente")
    parser.add_argument("--interval", type=float, default=60.0, help="segundos entre ciclos")
    args = parser.parse_args(argv)

    if not args.loop:
        return _run_once(args)

    try:
        while True:
            started = time.monotonic()
            _run_once(args)
            elapsed = time.monotonic() - started
            time.sleep(max(0.0, args.interval - elapsed))
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
