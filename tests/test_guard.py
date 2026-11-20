"""Proof that driftpatch never runs git push and connects only to the mock server or the model endpoint.

The whole `run` step executes under a Python audit hook (sys.addaudithook) that
records every subprocess.Popen and socket.connect event.
"""

import ipaddress
import socket
import subprocess

import pytest
from conftest import PY_CLIENT, TS_CLIENT, V1, V2, _real_connect

from driftpatch import guard
from driftpatch.cli import main
from driftpatch.guard import GuardViolation


def _check_events(events, allowed=()):
    for event in events:
        if event[0] == "subprocess":
            argv = event[1]
            assert not ("git" in [a.rsplit("/", 1)[-1] for a in argv] and "push" in argv), argv
        elif event[0] == "connect":
            host = event[1]
            assert host in allowed or ipaddress.ip_address(host).is_loopback, host


@pytest.mark.parametrize("client", [PY_CLIENT, TS_CLIENT])
def test_full_run_never_pushes_and_stays_local(tmp_path, client):
    guard.activate()
    try:
        code = main(["run", str(V1), str(V2), str(client), "--out", str(tmp_path / "out"), "--no-guard"])
        events = guard.events()
        blocked = guard.blocked()
    finally:
        guard.deactivate()
    assert code in (0, 1)
    assert blocked == []
    assert any(e[0] == "subprocess" for e in events), "the test runner should show up as a subprocess"
    _check_events(events)


def test_run_turns_the_guard_on_by_itself(tmp_path, monkeypatch):
    seen = {}
    real = guard.activate

    def spy(allowed_hosts=()):
        seen["allowed"] = set(allowed_hosts)
        real(allowed_hosts)

    monkeypatch.setattr(guard, "activate", spy)
    assert main(["run", str(V1), str(V2), str(PY_CLIENT), "--out", str(tmp_path / "out")]) == 0
    assert seen["allowed"] == set()  # rule proposer: no endpoint is allowed


@pytest.fixture
def no_repo(tmp_path, monkeypatch):
    """Run planted pushes from an empty folder outside any repo, so a broken guard still cannot push anything."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
    monkeypatch.delenv("GIT_DIR", raising=False)
    return tmp_path


def test_planted_git_push_is_blocked(no_repo):
    """Broken case: a planted `git push` call. The guard must stop it before it starts."""
    with guard.guarded():
        with pytest.raises(GuardViolation):
            subprocess.run(["git", "push", "origin", "HEAD"], timeout=5)
        with pytest.raises(GuardViolation):
            subprocess.run("git push", shell=True, timeout=5)
        assert len(guard.blocked()) == 2


def test_planted_remote_connect_is_blocked():
    """Broken case: a planted connection to 192.0.2.1. The audit hook fires before the connect."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with guard.guarded():
            with pytest.raises(GuardViolation):
                _real_connect(sock, ("192.0.2.1", 9))
            assert guard.blocked()[0][1] == "192.0.2.1"
    finally:
        sock.close()


def test_configured_endpoint_is_allowed():
    """The hook lets the configured endpoint through. Called directly so no packet leaves the machine."""
    with guard.guarded({"192.0.2.7"}):
        guard._hook("socket.connect", (None, ("192.0.2.7", 443)))
        with pytest.raises(GuardViolation):
            guard._hook("socket.connect", (None, ("192.0.2.8", 443)))
        assert [b[1] for b in guard.blocked()] == ["192.0.2.8"]


def test_guard_is_off_outside_the_block():
    with guard.guarded():
        pass
    subprocess.run(["git", "--version"], capture_output=True, timeout=10)
    assert guard.blocked() == []


def test_os_system_git_push_is_blocked(no_repo):
    """A push through os.system is caught too. The hook raises before any shell starts."""
    import os

    with guard.guarded(), pytest.raises(GuardViolation):
        os.system("git push origin main")  # noqa: S605, S607 (the guard stops it before it runs)
    assert guard.blocked()


def test_git_push_alias_is_blocked(no_repo):
    """`git -c alias.p=push p` hides the word push in an alias. The guard still sees it."""
    with guard.guarded(), pytest.raises(GuardViolation):
        subprocess.run(["git", "-c", "alias.p=push", "p"], capture_output=True, timeout=10)  # noqa: S603, S607


def test_harmless_git_is_allowed():
    with guard.guarded():
        subprocess.run(["git", "--version"], capture_output=True, timeout=10)  # noqa: S603, S607
    assert guard.blocked() == []


def test_name_lookup_of_a_remote_host_is_blocked():
    with guard.guarded(), pytest.raises(GuardViolation):
        socket.getaddrinfo("example.com", 443)
    assert guard.blocked()[0][:2] == ("lookup", "example.com")


def test_udp_send_to_a_remote_host_is_blocked():
    with guard.guarded(), socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s, pytest.raises(GuardViolation):
        s.sendto(b"x", ("192.0.2.9", 53))


@pytest.mark.parametrize("command", ["diff", "find", "patch"])
def test_every_command_runs_under_the_guard(monkeypatch, command):
    seen = []
    real = guard.activate
    monkeypatch.setattr(guard, "activate", lambda hosts=(): (seen.append(set(hosts)), real(hosts)))
    argv = [command, str(V1), str(V2)]
    if command != "diff":
        argv.append(str(PY_CLIENT))
    assert main(argv) == 0
    assert seen == [set()]


def test_census_runs_without_the_guard(monkeypatch, tmp_path):
    import driftpatch.census as census

    seen = []
    monkeypatch.setattr(guard, "activate", lambda hosts=(): seen.append(hosts))
    monkeypatch.setattr(census, "run_census", lambda *a, **k: None)
    assert main(["census", "--root", str(tmp_path)]) == 0
    assert seen == []
