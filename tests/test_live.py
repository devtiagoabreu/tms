import socket
from pathlib import Path

import pytest

from tms import collector
from tms.core import live as live_mod
from tms.core.live import (
    DATA_ERROR,
    NOT_SUPPORT,
    PING_TIMEOUT,
    error_status,
    live_to_monitor_state,
    parse_live,
)
from tms.core.state import NO_DATA, OFFLINE, RUN, STOPPED

FIXTURES = Path(__file__).parent / "fixtures"


def _lines(name: str) -> list[str]:
    return FIXTURES.joinpath(name).read_text(encoding="utf-8").splitlines()


def test_parse_jat710_complete():
    live = parse_live(_lines("live_jat710.txt"))
    assert live.mac_type == "JAT710"
    assert live.complete is True
    assert live.error is None
    assert live.stop == 1
    assert live.status == "Weft"
    assert live.duration == 125
    assert live.style == "2312"
    assert live.top_beam_use == 1
    assert live.value("rpm") == 558
    assert live.effic_shift == 82.5
    assert live.effic_24h == 80.1


def test_parse_lwt710_complete():
    live = parse_live(_lines("live_lwt710.txt"))
    assert live.mac_type == "LWT710"
    assert live.complete is True
    assert live.required_state == 15
    assert live.status == "CatchCode_front"
    assert live.duration == 42


def test_stop_zero_is_run():
    lines = [ln.replace("Stop=1", "Stop=0") for ln in _lines("live_jat710.txt")]
    live = parse_live(lines)
    assert live.stop == 0
    assert live.status == "Run"
    assert live.duration == 9000
    assert live_to_monitor_state(live) == RUN


def test_incomplete_payload_is_data_error():
    live = parse_live(["Machine_type=JAT710", "Stop=1", "Rpm=500"])
    assert live.complete is False
    assert live.error == DATA_ERROR
    assert live.status == "Data_error"
    assert live_to_monitor_state(live) == NO_DATA


def test_error_status_mapping():
    live = error_status(PING_TIMEOUT)
    assert live.status == "Power_off"
    assert live_to_monitor_state(live) == OFFLINE
    assert live_to_monitor_state(error_status(NOT_SUPPORT)) == NO_DATA
    assert live_to_monitor_state(error_status(live_mod.SOCKET_ERROR)) == OFFLINE


def test_stopped_state_from_bits():
    live = parse_live(_lines("live_jat710.txt"))
    assert live_to_monitor_state(live) == STOPPED


class _Response:
    def __init__(self, data: bytes):
        self._data = data

    def read(self) -> bytes:
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_fetch_live_parses_body(monkeypatch):
    body = "\n".join(_lines("live_jat710.txt")).encode("shift_jis")
    monkeypatch.setattr(
        collector.urllib.request, "urlopen", lambda url, timeout: _Response(body)
    )
    live = collector.fetch_live("10.0.0.1")
    assert live.complete is True
    assert live.status == "Weft"


def test_fetch_live_timeout(monkeypatch):
    def _raise(url, timeout):
        raise socket.timeout()

    monkeypatch.setattr(collector.urllib.request, "urlopen", _raise)
    live = collector.fetch_live("10.0.0.1", timeout=0.1)
    assert live.error == PING_TIMEOUT


def test_fetch_live_not_supported(monkeypatch):
    body = b"Not supported."
    monkeypatch.setattr(
        collector.urllib.request, "urlopen", lambda url, timeout: _Response(body)
    )
    assert collector.fetch_live("10.0.0.1").error == NOT_SUPPORT


def test_collect_builds_mapping(monkeypatch):
    body = "\n".join(_lines("live_lwt710.txt")).encode("utf-8")
    monkeypatch.setattr(
        collector.urllib.request, "urlopen", lambda url, timeout: _Response(body)
    )
    result = collector.collect([("00001", "10.0.0.1"), ("00002", "10.0.0.2")])
    assert set(result) == {"00001", "00002"}
    assert result["00001"].status == "CatchCode_front"
