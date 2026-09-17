"""Helpers comuns aos parsers de ingestão."""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional, Sequence


def split_kv(segment: str) -> tuple[Optional[str], str]:
    """Divide `"chave valor..."` em (chave, valor). Sem chave → (None, "")."""
    segment = segment.strip()
    if not segment:
        return None, ""
    head, _, tail = segment.partition(" ")
    return head, tail.strip()


def parse_kv_line(line: str) -> Dict[str, str]:
    """Linha `,k v,k v,...` (snapshot) → dict ordenado chave→valor.

    Chaves repetidas: a última vence (como no legado).
    """
    result: Dict[str, str] = {}
    for segment in line.rstrip("\r\n").split(","):
        key, value = split_kv(segment)
        if key:
            result[key] = value
    return result


def unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        return value[1:-1]
    return value


def to_int(value: str, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def to_float(value: str, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def parse_int_list(value: str) -> List[int]:
    return [to_int(tok) for tok in value.split()]


def parse_float_list(value: str) -> List[float]:
    return [to_float(tok) for tok in value.split()]


def parse_timestamp(tokens: Sequence[str]) -> Optional[datetime]:
    """`y m d w H M S` → datetime (o campo `w`/weekday é ignorado).

    Retorna ``None`` para valores ausentes/inválidos (ex.: ``"-"``).
    """
    if len(tokens) < 7:
        return None
    y, mo, d, _w, h, mi, s = tokens[:7]
    try:
        return datetime(int(y), int(mo), int(d), int(h), int(mi), int(s))
    except (TypeError, ValueError):
        return None


def split_sections(lines: Sequence[str], marker: str) -> List[List[str]]:
    """Divide linhas em blocos começando por `marker` (o marcador é incluído)."""
    blocks: List[List[str]] = []
    current: Optional[List[str]] = None
    for line in lines:
        if line.startswith(marker):
            if current is not None:
                blocks.append(current)
            current = [line]
        elif current is not None:
            current.append(line)
    if current is not None:
        blocks.append(current)
    return blocks
