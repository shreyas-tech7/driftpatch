"""A runtime guard built on Python audit hooks (sys.addaudithook).

While it is active it records every process launch (subprocess, os.system,
os.exec*, os.spawn*, os.posix_spawn*) and every socket connect, send and name
lookup in this process. It blocks any git command that mentions `push`
(which also catches an alias such as `git -c alias.p=push p`) and any
connection or lookup that is not for a loopback address or a host on the allow
list (the configured model endpoint). Audit hooks cannot be removed, so the
hook is installed once and switched on and off with a flag.

The hook sees only this process. The client's own tests run as child
processes and are not covered.
"""

import ipaddress
import os
import sys
import threading

_state = {"installed": False, "active": False, "allowed_hosts": set(), "events": [], "blocked": []}
_lock = threading.Lock()


class GuardViolation(PermissionError):
    pass


def _is_loopback(host) -> bool:
    if host in ("localhost", ""):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _tokens(argv):
    if isinstance(argv, (str, bytes, os.PathLike)):
        return os.fsdecode(argv).split()
    return [t for a in (argv or []) for t in os.fsdecode(a).split()]


def _is_git_push(argv) -> bool:
    """True for any git command that mentions push, also inside a shell string or an alias definition."""
    tokens = [t.strip("'\";&|()") for t in _tokens(argv)]
    names = [os.path.basename(t) for t in tokens]
    return any(n in ("git", "git.exe") for n in names) and any("push" in t.lower() for t in tokens)


# event name -> index of the argv (or command string) in the audit args
_SPAWN_EVENTS = {"subprocess.Popen": 1, "os.system": 0, "os.exec": 1, "os.spawn": 2, "os.posix_spawn": 1}
_NET_EVENTS = {"socket.connect": 1, "socket.sendto": 1, "socket.sendmsg": 1}


def _check_host(host, record):
    if not _is_loopback(host) and host not in _state["allowed_hosts"]:
        with _lock:
            _state["blocked"].append(record)
        raise GuardViolation(f"driftpatch blocked a network connection to {host}")


def _hook(event, args):
    if not _state["active"]:
        return
    if event in _SPAWN_EVENTS:
        argv = args[_SPAWN_EVENTS[event]] if len(args) > _SPAWN_EVENTS[event] else None
        parts = [argv] if isinstance(argv, (str, bytes, os.PathLike)) else list(argv or [])
        if event == "subprocess.Popen" and args[0] is not None:
            parts = [args[0], *parts]  # an explicit executable= counts too
        record = ("subprocess", [os.fsdecode(a) for a in parts])
        with _lock:
            _state["events"].append(record)
        if _is_git_push(parts):
            with _lock:
                _state["blocked"].append(record)
            raise GuardViolation("driftpatch never runs git push")
    elif event in _NET_EVENTS:
        address = args[_NET_EVENTS[event]]
        if isinstance(address, tuple) and address:
            host = str(address[0])
            record = ("connect", host, address[1] if len(address) > 1 else None)
            with _lock:
                _state["events"].append(record)
            _check_host(host, record)
    elif event == "socket.getaddrinfo":
        host = args[0]
        if host is not None:
            host = os.fsdecode(host) if isinstance(host, bytes) else str(host)
            record = ("lookup", host, args[1] if len(args) > 1 else None)
            with _lock:
                _state["events"].append(record)
            _check_host(host, record)


def activate(allowed_hosts=()):
    """Start recording and blocking. allowed_hosts holds resolved IPs or names that may be contacted."""
    with _lock:
        if not _state["installed"]:
            sys.addaudithook(_hook)
            _state["installed"] = True
        _state["allowed_hosts"] = set(allowed_hosts)
        _state["events"] = []
        _state["blocked"] = []
        _state["active"] = True


def deactivate():
    with _lock:
        _state["active"] = False


def events():
    with _lock:
        return list(_state["events"])


def blocked():
    with _lock:
        return list(_state["blocked"])


class guarded:
    """Context manager: `with guarded(allowed_hosts): ...`."""

    def __init__(self, allowed_hosts=()):
        self.allowed_hosts = allowed_hosts

    def __enter__(self):
        activate(self.allowed_hosts)
        return self

    def __exit__(self, *exc):
        deactivate()
        return False
