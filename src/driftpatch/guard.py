"""A runtime guard built on Python audit hooks (sys.addaudithook).

While it is active it records every subprocess launch and socket connect in
this process. It blocks any `git push` and any connection that is not to a
loopback address or to a host on the allow list (the configured model
endpoint). Audit hooks cannot be removed, so the hook is installed once and
switched on and off with a flag.
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


def _is_git_push(argv) -> bool:
    """True for `git push ...`, also when wrapped in a shell string such as `sh -c "git push"`."""
    if isinstance(argv, (str, bytes)):
        tokens = os.fsdecode(argv).split()
    else:
        tokens = [t for a in (argv or []) for t in os.fsdecode(a).split()]
    names = [os.path.basename(t.strip("'\"")) for t in tokens]
    return "git" in names and "push" in [t.strip("'\"") for t in tokens]


def _hook(event, args):
    if not _state["active"]:
        return
    if event == "subprocess.Popen":
        argv = args[1]
        record = ("subprocess", [os.fsdecode(a) for a in (argv if isinstance(argv, (list, tuple)) else [argv])])
        with _lock:
            _state["events"].append(record)
        if _is_git_push(argv):
            with _lock:
                _state["blocked"].append(record)
            raise GuardViolation("driftpatch never runs git push")
    elif event == "socket.connect":
        address = args[1]
        if isinstance(address, tuple) and address:
            host = str(address[0])
            record = ("connect", host, address[1] if len(address) > 1 else None)
            with _lock:
                _state["events"].append(record)
            if not _is_loopback(host) and host not in _state["allowed_hosts"]:
                with _lock:
                    _state["blocked"].append(record)
                raise GuardViolation(f"driftpatch blocked a network connection to {host}")


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
