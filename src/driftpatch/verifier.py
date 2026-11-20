"""The verifier. It is the hard gate.

It copies the client to a temp folder, starts a mock server from the new spec,
and runs the client's own tests twice: once on the unpatched copy and once on
the patched copy. A patch passes only when:

1. it applies cleanly and touches no test file,
2. every test that failed before now passes,
3. no test that passed before now fails,
4. the same tests ran both times, and at least one ran.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .mock_server import MockServer
from .patch import PatchError, apply_diff, files_in_diff, write_files

DEFAULT_TIMEOUT = 120
_IGNORE = shutil.ignore_patterns("__pycache__", ".pytest_cache", "node_modules", "*.pyc", ".venv")


def detect_language(client_dir) -> str:
    client_dir = Path(client_dir)
    if (client_dir / "package.json").exists():
        return "ts"
    if (client_dir / "pyproject.toml").exists() or any(client_dir.rglob("*.py")):
        return "python"
    raise ValueError(f"cannot tell the language of the client in {client_dir}")


def is_test_file(rel: str) -> bool:
    parts = Path(rel).parts
    name = Path(rel).name
    return (
        any(p in ("tests", "test", "__tests__") for p in parts[:-1])
        or name.startswith("test_")
        or name.endswith(("_test.py", ".test.ts", ".spec.ts", ".test.js"))
        or name == "conftest.py"
    )


@dataclass
class TestRun:
    results: dict = field(default_factory=dict)  # test name -> True (pass) or False
    returncode: int = 0
    error: str = ""
    output_tail: str = ""

    @property
    def passed(self):
        return sorted(n for n, ok in self.results.items() if ok)

    @property
    def failed(self):
        return sorted(n for n, ok in self.results.items() if not ok)


def _parse_junit(xml_path: Path) -> dict:
    results = {}
    if not xml_path.exists():
        return results
    root = ET.parse(xml_path).getroot()
    for case in root.iter("testcase"):
        name = f"{case.get('classname', '')}::{case.get('name', '')}".strip(":")
        bad = any(child.tag in ("failure", "error") for child in case) or case.get("failure")
        skipped = any(child.tag == "skipped" for child in case)
        if skipped:
            continue
        results[name] = not bad
    return results


def run_tests(client_dir, base_url, language=None, timeout=DEFAULT_TIMEOUT) -> TestRun:
    """Run the client's tests against base_url. client_dir must already be a temp copy."""
    client_dir = Path(client_dir)
    language = language or detect_language(client_dir)
    report = client_dir / ".driftpatch-junit.xml"
    env = {k: v for k, v in os.environ.items() if not k.endswith(("_API_KEY", "_TOKEN", "_SECRET"))}
    env.update(ACME_BASE_URL=base_url, DRIFTPATCH_BASE_URL=base_url, PYTHONDONTWRITEBYTECODE="1", NO_COLOR="1")
    if language == "python":
        cmd = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-o", "addopts=", f"--junitxml={report}"]
    elif language == "ts":
        tests = sorted(str(p.relative_to(client_dir)) for p in client_dir.rglob("*.test.ts") if "node_modules" not in p.parts)
        if not tests:
            return TestRun(error="no *.test.ts files found")
        cmd = ["node", "--test", "--test-reporter=junit", f"--test-reporter-destination={report}", *tests]
    else:
        raise ValueError(f"unknown language {language!r}")
    try:
        proc = subprocess.run(cmd, cwd=client_dir, env=env, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return TestRun(returncode=-1, error=f"tests timed out after {timeout}s")
    except FileNotFoundError as err:
        return TestRun(returncode=-1, error=f"test runner not found: {err.filename}")
    try:
        results = _parse_junit(report)
    except ET.ParseError as err:
        return TestRun(returncode=proc.returncode, error=f"could not read the test report: {err}")
    tail = (proc.stdout + proc.stderr)[-2000:]
    error = "" if results else "no test results (the tests may not have been collected)"
    return TestRun(results=results, returncode=proc.returncode, error=error, output_tail=tail)


@dataclass
class Verification:
    verdict: str  # "pass" or "fail"
    reasons: list = field(default_factory=list)
    before_passed: list = field(default_factory=list)
    before_failed: list = field(default_factory=list)
    after_passed: list = field(default_factory=list)
    after_failed: list = field(default_factory=list)
    fixed: list = field(default_factory=list)
    regressions: list = field(default_factory=list)
    still_failing: list = field(default_factory=list)
    files: list = field(default_factory=list)
    language: str = ""

    @property
    def passed(self) -> bool:
        return self.verdict == "pass"

    @property
    def after_pass_rate(self) -> float:
        total = len(self.after_passed) + len(self.after_failed)
        return len(self.after_passed) / total if total else 0.0

    def to_dict(self):
        d = asdict(self)
        d["after_pass_rate"] = round(self.after_pass_rate, 4)
        return d


def _copy(client_dir, dest):
    shutil.copytree(client_dir, dest, ignore=_IGNORE)
    return Path(dest)


def baseline(spec: dict, client_dir, timeout=DEFAULT_TIMEOUT) -> TestRun:
    """Run the unpatched client's tests against the mock server for spec."""
    language = detect_language(client_dir)
    with tempfile.TemporaryDirectory(prefix="driftpatch-") as tmp, MockServer(spec) as server:
        work = _copy(client_dir, Path(tmp) / "client")
        return run_tests(work, server.url, language, timeout)


def verify(spec: dict, client_dir, diff_text: str, timeout=DEFAULT_TIMEOUT, before: TestRun = None) -> Verification:
    """Gate a patch. diff_text is a unified diff relative to client_dir."""
    client_dir = Path(client_dir)
    language = detect_language(client_dir)
    files = files_in_diff(diff_text) if diff_text else []
    reasons = []
    if not diff_text or not files:
        return Verification("fail", ["the patch is empty"], language=language)
    touched_tests = [f for f in files if is_test_file(f)]
    if touched_tests:
        return Verification("fail", [f"the patch edits test files: {', '.join(touched_tests)}"], files=files, language=language)
    try:
        new_files = apply_diff(diff_text, client_dir)
    except (PatchError, OSError, UnicodeDecodeError) as err:
        return Verification("fail", [f"the patch does not apply: {err}"], files=files, language=language)
    if before is None:
        before = baseline(spec, client_dir, timeout)
    with tempfile.TemporaryDirectory(prefix="driftpatch-") as tmp, MockServer(spec) as server:
        work = _copy(client_dir, Path(tmp) / "client")
        write_files(work, new_files)
        after = run_tests(work, server.url, language, timeout)
    if before.error:
        reasons.append(f"baseline run: {before.error}")
    if after.error:
        reasons.append(f"patched run: {after.error}")
    fixed = sorted(n for n in before.failed if after.results.get(n) is True)
    regressions = sorted(n for n in before.passed if after.results.get(n) is not True)
    still_failing = sorted(n for n in before.failed if after.results.get(n) is not True)
    if set(before.results) != set(after.results):
        reasons.append("the patched run did not run the same tests")
    if not after.results:
        reasons.append("no tests ran")
    if not before.failed:
        reasons.append("no test failed before the patch, so there was nothing to fix")
    if still_failing:
        reasons.append(f"{len(still_failing)} test(s) still fail")
    if regressions:
        reasons.append(f"{len(regressions)} test(s) that passed before now fail")
    verdict = "fail" if reasons else "pass"
    return Verification(
        verdict,
        reasons,
        before.passed,
        before.failed,
        after.passed,
        after.failed,
        fixed,
        regressions,
        still_failing,
        files,
        language,
    )
