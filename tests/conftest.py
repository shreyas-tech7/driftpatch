"""Test guard: any network connection to a host that is not local fails the test."""

import ipaddress
import socket

import pytest

_real_connect = socket.socket.connect
_real_connect_ex = socket.socket.connect_ex


class NetworkBlocked(RuntimeError):
    pass


def _is_local(address) -> bool:
    if isinstance(address, (str, bytes)):  # AF_UNIX path
        return True
    host = address[0]
    if host in ("localhost", ""):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _guarded_connect(self, address):
    if not _is_local(address):
        raise NetworkBlocked(f"test tried to open a network connection to {address!r}")
    return _real_connect(self, address)


def _guarded_connect_ex(self, address):
    if not _is_local(address):
        raise NetworkBlocked(f"test tried to open a network connection to {address!r}")
    return _real_connect_ex(self, address)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    monkeypatch.setattr(socket.socket, "connect", _guarded_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", _guarded_connect_ex)
    yield


ROOT = __import__("pathlib").Path(__file__).resolve().parent.parent
V1 = ROOT / "examples/acme/specs/acme-orders-v1.json"
V2 = ROOT / "examples/acme/specs/acme-orders-v2.json"
PY_CLIENT = ROOT / "examples/acme/clients/python"
TS_CLIENT = ROOT / "examples/acme/clients/ts"


@pytest.fixture
def v1():
    import json

    return json.loads(V1.read_text())


def case(case_id):
    import json

    return json.loads((ROOT / "bench/cases" / case_id / "case.json").read_text())
