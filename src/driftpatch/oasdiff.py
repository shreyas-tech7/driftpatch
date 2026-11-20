"""Adapter for the optional oasdiff binary.

oasdiff knows more than 100 kinds of breaking change. driftpatch uses its
findings for the report and maps each id to one of the built-in kinds where it
can. oasdiff does not detect renames: it reports a removed property and an
added one. The built-in differ still drives the patch.
"""

import json
import shutil
import subprocess

from . import differ

# Ordered: the first matching rule wins.
_ID_RULES = [
    ("api-path-removed", differ.REMOVED_ENDPOINT),
    ("api-removed", differ.REMOVED_ENDPOINT),
    ("new-required-request-parameter", differ.NEW_REQUIRED_PARAMETER),
    ("request-parameter-became-required", differ.NEW_REQUIRED_PARAMETER),
    ("new-required-request-property", differ.NEW_REQUIRED_PARAMETER),
    ("request-property-became-required", differ.NEW_REQUIRED_PARAMETER),
    ("enum-value-removed", differ.CHANGED_ENUM),
    ("enum-value-added", differ.CHANGED_ENUM),
    ("type-changed", differ.CHANGED_TYPE),
    ("type-generalized", differ.CHANGED_TYPE),
    ("property-removed", differ.REMOVED_FIELD),
    ("request-parameter-removed", differ.REMOVED_FIELD),
]


class OasdiffError(RuntimeError):
    pass


def binary():
    return shutil.which("oasdiff")


def available() -> bool:
    return binary() is not None


def kind_for(check_id: str) -> str:
    for needle, kind in _ID_RULES:
        if needle in check_id:
            return kind
    return "other"


def breaking(old_path, new_path, timeout=120) -> list:
    """Run `oasdiff breaking` on two local files. Returns a list of finding dicts with a `kind` key."""
    exe = binary()
    if exe is None:
        raise OasdiffError("oasdiff is not installed")
    cmd = [exe, "breaking", str(old_path), str(new_path), "--format", "json", "--allow-external-refs=false"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as err:
        raise OasdiffError(f"oasdiff timed out after {timeout}s") from err
    if proc.returncode not in (0, 1):
        raise OasdiffError(f"oasdiff failed ({proc.returncode}): {proc.stderr.strip()[:400]}")
    try:
        findings = json.loads(proc.stdout or "[]") or []
    except json.JSONDecodeError as err:
        raise OasdiffError(f"oasdiff printed invalid JSON: {err}") from err
    out = []
    for f in findings:
        out.append(
            {
                "id": f.get("id", ""),
                "kind": kind_for(f.get("id", "")),
                "level": f.get("level"),
                "operation": f.get("operation", ""),
                "path": f.get("path", ""),
                "text": f.get("text", ""),
            }
        )
    return out


def count_by_kind(findings) -> dict:
    counts = {}
    for f in findings:
        counts[f["kind"]] = counts.get(f["kind"], 0) + 1
    return counts
