"""The benchmark runner.

It runs the full pipeline on every frozen case in bench/cases and scores the
proposer. Before it runs, it checks the SHA-256 manifest, so an edited case
stops the run.
"""

import hashlib
import json
import os
import platform
import random
import statistics
import time
from datetime import UTC, datetime
from pathlib import Path

from .patch import diff_size
from .pipeline import Run
from .proposer_llm import LLMProposer, RecordError, ReplayMissing
from .proposer_oracle import OracleProposer
from .proposer_rule import RuleProposer

BOOTSTRAP_SEED = 7
BOOTSTRAP_ROUNDS = 2000


class ManifestError(RuntimeError):
    pass


def check_manifest(root) -> int:
    root = Path(root)
    manifest = root / "bench" / "MANIFEST.sha256"
    count = 0
    for line in manifest.read_text().splitlines():
        if not line.strip():
            continue
        digest, rel = line.split("  ", 1)
        path = root / rel
        if not path.exists():
            raise ManifestError(f"missing frozen file: {rel}")
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ManifestError(f"frozen file changed: {rel}")
        count += 1
    listed = {line.split("  ", 1)[1] for line in manifest.read_text().splitlines() if line.strip()}
    for p in (root / "bench" / "cases").rglob("*"):
        if p.is_file() and p.relative_to(root).as_posix() not in listed:
            raise ManifestError(f"case file not in the manifest: {p.relative_to(root).as_posix()}")
    return count


def load_cases(root, split="all"):
    root = Path(root)
    cases = []
    for path in sorted((root / "bench" / "cases").glob("C*/case.json")):
        case = json.loads(path.read_text())
        if split == "all" or case["split"] == split:
            cases.append(case)
    return cases


def wilson(k: int, n: int, z: float = 1.959964):
    if n == 0:
        return [0.0, 0.0]
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / denom
    return [round(max(0.0, centre - half), 4), round(min(1.0, centre + half), 4)]


def bootstrap_mean(values, seed=BOOTSTRAP_SEED, rounds=BOOTSTRAP_ROUNDS):
    if not values:
        return [0.0, 0.0]
    rng = random.Random(seed)  # noqa: S311 (bootstrap resampling, not security)
    means = sorted(statistics.fmean(rng.choices(values, k=len(values))) for _ in range(rounds))
    return [round(means[int(0.025 * rounds)], 4), round(means[int(0.975 * rounds) - 1], 4)]


def make_proposer(name, case, root, llm_mode="replay"):
    if name == "rule":
        return RuleProposer()
    if name == "oracle":
        return OracleProposer((Path(root) / case["expected_patch"]).read_text())
    if name == "llm":
        return LLMProposer(mode=llm_mode, fixtures_dir=Path(root) / "fixtures" / "llm")
    raise ValueError(f"unknown proposer {name!r}")


def run_case(case, root, proposer_name, llm_mode="replay", timeout=120):
    root = Path(root)
    started = time.perf_counter()
    run = Run(
        str(root / case["old_spec"]),
        str(root / case["new_spec"]),
        str(root / case["client"]),
        make_proposer(proposer_name, case, root, llm_mode),
        timeout=timeout,
    )
    error = ""
    try:
        run.run()
    except (ReplayMissing, RecordError) as err:
        error = f"not run: {err}"
    v = run.verification
    p = run.proposal
    return {
        "id": case["id"],
        "title": case["title"],
        "language": case["language"],
        "split": case["split"],
        "kinds": sorted({c.kind for c in run.changes}),
        "outcome": run.outcome or "error",
        "verified": run.verified,
        "error": error,
        "tests_total": (len(v.after_passed) + len(v.after_failed)) if v else None,
        "tests_failing_before": len(v.before_failed) if v else None,
        "after_pass_rate": round(v.after_pass_rate, 4) if v else None,
        "regressions": len(v.regressions) if v else 0,
        "patch_lines": diff_size(p.diff) if p and p.diff else 0,
        "tokens": p.tokens if p else 0,
        "declined": [reason for _, reason in (p.declined if p else [])],
        "seconds": round(time.perf_counter() - started, 3),
    }


def summarize(rows, baseline_rates):
    ran = [r for r in rows if not r["error"]]
    n = len(ran)
    k = sum(r["verified"] for r in ran)
    rates = [r["after_pass_rate"] if r["after_pass_rate"] is not None else baseline_rates.get(r["id"], 0.0) for r in ran]
    sizes = [r["patch_lines"] for r in ran if r["patch_lines"]]
    return {
        "cases": n,
        "not_run": len(rows) - n,
        "verified": k,
        "verified_rate": round(k / n, 4) if n else None,
        "verified_ci95": wilson(k, n),
        "test_pass_rate": round(statistics.fmean(rates), 4) if rates else None,
        "test_pass_rate_ci95": bootstrap_mean(rates),
        "regressions": sum(r["regressions"] for r in ran),
        "patch_lines_median": statistics.median(sizes) if sizes else 0,
        "patches_proposed": sum(1 for r in ran if r["patch_lines"]),
        "tokens": sum(r["tokens"] for r in ran),
    }


def baseline_rates(root, cases, timeout=120):
    """Unpatched test pass rate per case, used when a proposer offers no patch."""
    from .spec import load_spec
    from .verifier import baseline

    rates = {}
    for case in cases:
        run = baseline(load_spec(Path(root) / case["new_spec"]), Path(root) / case["client"], timeout)
        total = len(run.results)
        rates[case["id"]] = round(len(run.passed) / total, 4) if total else 0.0
    return rates


def cpu_model():
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or "unknown"


def run_bench(root, proposer_name, split="all", llm_mode="replay", timeout=120, progress=None):
    root = Path(root)
    frozen = check_manifest(root)
    cases = load_cases(root, split)
    started = time.perf_counter()
    rows = []
    for case in cases:
        rows.append(run_case(case, root, proposer_name, llm_mode, timeout))
        if progress:
            progress(rows[-1])
    rates = baseline_rates(root, cases, timeout)
    elapsed = time.perf_counter() - started
    groups = {"all": rows, "dev": [r for r in rows if r["split"] == "dev"], "heldout": [r for r in rows if r["split"] == "heldout"]}
    status = "not run" if rows and all(r["error"] for r in rows) else "ok"
    return {
        "meta": {
            "proposer": proposer_name,
            "status": status,
            "model": "none (rules)" if proposer_name == "rule" else "none (answer key)" if proposer_name == "oracle" else "see fixtures",
            "llm_mode": llm_mode if proposer_name == "llm" else None,
            "date": datetime.now(UTC).strftime("%Y-%m-%d"),
            "seed": f"none for the pipeline (deterministic). Bootstrap seed {BOOTSTRAP_SEED}, {BOOTSTRAP_ROUNDS} rounds.",
            "cpu": cpu_model(),
            "cores_available": len(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else os.cpu_count(),
            "python": platform.python_version(),
            "frozen_files_checked": frozen,
            "seconds": round(elapsed, 2),
        },
        "summary": {name: summarize(group, rates) for name, group in groups.items()},
        "unpatched_test_pass_rate": rates,
        "cases": rows,
    }
