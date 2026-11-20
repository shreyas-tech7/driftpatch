"""The frozen benchmark: manifest, split, size and statistics."""

import json
import shutil
import subprocess
import sys

import pytest
from conftest import ROOT

from driftpatch import bench


def test_manifest_matches():
    assert bench.check_manifest(ROOT) > 30


def test_at_least_30_cases_with_a_fixed_split():
    cases = bench.load_cases(ROOT)
    assert len(cases) >= 30
    assert sum(c["split"] == "dev" for c in cases) == 25
    assert sum(c["split"] == "heldout" for c in cases) == len(cases) - 25
    assert {c["language"] for c in cases} == {"python", "ts"}


def test_tampered_case_stops_the_run(tmp_path):
    copy = tmp_path / "repo"
    for part in ("bench", "examples"):
        shutil.copytree(ROOT / part, copy / part)
    target = copy / "bench/cases/C001/expected.diff"
    target.write_text(target.read_text() + "\n")
    with pytest.raises(bench.ManifestError):
        bench.check_manifest(copy)


def test_extra_case_file_stops_the_run(tmp_path):
    copy = tmp_path / "repo"
    for part in ("bench", "examples"):
        shutil.copytree(ROOT / part, copy / part)
    (copy / "bench/cases/C001/extra.json").write_text("{}")
    with pytest.raises(bench.ManifestError):
        bench.check_manifest(copy)


def test_make_cases_check_passes():
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts/make_cases.py"), "--check"], capture_output=True, text=True, timeout=120, cwd=ROOT
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_every_case_has_an_answer_key():
    for c in bench.load_cases(ROOT):
        assert (ROOT / c["expected_patch"]).read_text().startswith("--- a/")


def test_wilson_interval():
    lo, hi = bench.wilson(22, 36)
    assert 0.44 < lo < 0.47 and 0.74 < hi < 0.77
    assert bench.wilson(0, 0) == [0.0, 0.0]


def test_bootstrap_is_seeded():
    values = [0.5, 1.0, 0.8, 1.0, 0.2]
    assert bench.bootstrap_mean(values) == bench.bootstrap_mean(values)
    lo, hi = bench.bootstrap_mean(values)
    assert lo <= sum(values) / len(values) <= hi


def test_one_case_end_to_end():
    case = json.loads((ROOT / "bench/cases/C001/case.json").read_text())
    row = bench.run_case(case, ROOT, "oracle")
    assert row["verified"] and row["regressions"] == 0 and row["patch_lines"] > 0
