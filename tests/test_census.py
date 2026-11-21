"""The census, offline: a fake tag list and fake downloads built from the Acme specs."""

import json

from conftest import V1, V2

from driftpatch import census


def test_version_order():
    tags = ["v1.0.0", "v0.0.2", "v1.0.0-rc.2", "v1.0.0-rc.10", "v10", "v9", "v2.1.0"]
    ordered = sorted(tags, key=census.version_key)
    assert ordered.index("v1.0.0-rc.2") < ordered.index("v1.0.0-rc.10") < ordered.index("v1.0.0")
    assert ordered.index("v9") < ordered.index("v10")


def test_sample_keeps_ends_and_count():
    tags = [f"v{i}" for i in range(1, 2603)]
    picked = census.sample(tags, 20)
    assert len(picked) == 20 and picked[0] == "v1" and picked[-1] == "v2602"
    assert census.sample(["v2", "v1"], 20) == ["v1", "v2"]


def test_cache_names_are_hashed_and_reused(tmp_path):
    calls = []

    def fetch(url):
        calls.append(url)
        return b"{}"

    a = census.cached_fetch("https://example.org/a.json", tmp_path, fetch)
    b = census.cached_fetch("https://example.org/a.json", tmp_path, fetch)
    assert a == b and len(calls) == 1 and len(a.stem) == 64


def test_run_census_offline(tmp_path):
    specs = {"v1": V1.read_bytes(), "v2": V2.read_bytes(), "v3": V2.read_bytes()}

    def lister(url):
        return ["v3", "v1", "v2"]

    def fetch_by_tag(url):
        for tag, data in specs.items():
            if f"/{tag}/" in url:
                return data
        raise AssertionError(url)

    data = census.run_census(
        tmp_path, repos=["stripe"], samples=20, cache=tmp_path / "cache", lister=lister, fetch=fetch_by_tag, use_oasdiff=False
    )
    res = data["repos"]["stripe"]
    assert res["tags_sampled"] == ["v1", "v2", "v3"]
    assert [p["builtin_total"] for p in res["pairs"]] == [3, 0]
    assert res["builtin_totals"]["renamed-field"] == 1 and res["pairs_with_breaking"] == 1
    saved = json.loads((tmp_path / "results/census.json").read_text())
    assert saved["repos"]["stripe"]["builtin_total"] == 3
    md = (tmp_path / "docs/CENSUS.md").read_text()
    assert "## Method" in md and "| stripe/openapi | 3 | 2 | 1 |" in md
