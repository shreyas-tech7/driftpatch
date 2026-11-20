"""Time the full rule-baseline benchmark and fail if it goes over the limit.

Run it pinned to two cores:  taskset -c 0,1 .venv/bin/python scripts/time_bench.py --limit 600
It writes results/bench-rule.json and results/timing.json.
"""

import argparse
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from driftpatch.bench import cpu_model, run_bench  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=float, default=600)
    args = ap.parse_args()
    cores = len(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else os.cpu_count()
    started = time.perf_counter()
    result = run_bench(ROOT, "rule")
    seconds = time.perf_counter() - started
    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / "results/bench-rule.json").write_text(json.dumps(result, indent=2) + "\n")
    timing = {
        "date": datetime.now(UTC).strftime("%Y-%m-%d"),
        "seconds": round(seconds, 1),
        "limit": args.limit,
        "cores": cores,
        "cpu": cpu_model(),
        "cases": result["summary"]["all"]["cases"],
        "within_limit": seconds < args.limit,
    }
    (ROOT / "results/timing.json").write_text(json.dumps(timing, indent=2) + "\n")
    print(f"rule bench: {seconds:.1f} s on {cores} cores (limit {args.limit:.0f} s)")
    return 0 if timing["within_limit"] else 1


if __name__ == "__main__":
    sys.exit(main())
