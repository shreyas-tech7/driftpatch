"""Census of breaking changes across real OpenAPI spec histories.

Method, in short:

1. List the repo's tags with `git ls-remote --tags` (no clone).
2. Sort them by version and take about 20, evenly spaced, always the first and the last.
3. Download the spec file at each sampled tag from raw.githubusercontent.com into a cache
   whose file names are the SHA-256 of the URL.
4. Run the built-in differ on each consecutive pair, and oasdiff too when it is installed.
5. Write results/census.json and docs/CENSUS.md from the counts.
"""

import hashlib
import json
import re
import subprocess
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

from . import differ, oasdiff
from .spec import load_spec

REPOS = {
    "stripe": {"owner": "stripe", "repo": "openapi", "path": "openapi/spec3.json"},
    "github": {"owner": "github", "repo": "rest-api-description", "path": "descriptions/api.github.com/api.github.com.json"},
}
TIMEOUT = 120


def git_url(r):
    return f"https://github.com/{r['owner']}/{r['repo']}"


def raw_url(r, tag):
    return f"https://raw.githubusercontent.com/{r['owner']}/{r['repo']}/{tag}/{r['path']}"


def list_tags(url, timeout=TIMEOUT):
    out = subprocess.run(["git", "ls-remote", "--tags", url], capture_output=True, text=True, timeout=timeout, check=True).stdout  # noqa: S603, S607 (fixed argv, no shell, git from PATH)
    tags = []
    for line in out.splitlines():
        ref = line.split("\t")[-1]
        if ref.startswith("refs/tags/") and not ref.endswith("^{}"):
            tags.append(ref[len("refs/tags/") :])
    return tags


def version_key(tag):
    """v1.0.0-rc.2 sorts before v1.0.0, and v10 after v9."""
    main, _, pre = tag.lstrip("vV").partition("-")
    nums = tuple(int(n) for n in re.findall(r"\d+", main))
    pre_key = tuple(int(p) if p.isdigit() else p for p in re.split(r"[.]", pre)) if pre else ()
    return (nums, 0 if pre else 1, tuple(str(p).zfill(8) for p in pre_key))


def sample(tags, count):
    ordered = sorted(set(tags), key=version_key)
    if len(ordered) <= count:
        return ordered
    picks = sorted({round(i * (len(ordered) - 1) / (count - 1)) for i in range(count)})
    return [ordered[i] for i in picks]


def http_get(url, timeout=TIMEOUT):
    with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310 (https URLs built above)
        return resp.read()


def cached_fetch(url, cache, fetch=http_get):
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / (hashlib.sha256(url.encode()).hexdigest() + ".json")
    if not path.exists():
        data = fetch(url)
        json.loads(data)  # refuse to cache something that is not JSON
        path.write_bytes(data)
    return path


def census_repo(name, r, samples, cache, lister=list_tags, fetch=http_get, use_oasdiff=None):
    use_oasdiff = oasdiff.available() if use_oasdiff is None else use_oasdiff
    tags = lister(git_url(r))
    picked = sample(tags, samples)
    files = {t: cached_fetch(raw_url(r, t), cache, fetch) for t in picked}
    pairs = []
    for old, new in zip(picked, picked[1:], strict=False):
        changes = differ.diff_specs(load_spec(files[old]), load_spec(files[new]))
        row = {"from": old, "to": new, "builtin": differ.count_by_kind(changes), "builtin_total": len(changes)}
        if use_oasdiff:
            try:
                found = oasdiff.breaking(files[old], files[new], timeout=600)
                row["oasdiff"] = oasdiff.count_by_kind(found)
                row["oasdiff_total"] = len(found)
            except oasdiff.OasdiffError as err:
                row["oasdiff_error"] = str(err)[:200]
        row["examples"] = [c.describe() for c in changes[:3]]
        pairs.append(row)
    totals = {k: sum(p["builtin"].get(k, 0) for p in pairs) for k in differ.KINDS}
    result = {
        "repo": f"{r['owner']}/{r['repo']}",
        "file": r["path"],
        "tags_listed": len(set(tags)),
        "tags_sampled": picked,
        "pairs": pairs,
        "builtin_totals": totals,
        "builtin_total": sum(totals.values()),
        "pairs_with_breaking": sum(1 for p in pairs if p["builtin_total"]),
    }
    if use_oasdiff and pairs and all("oasdiff" in p for p in pairs):
        kinds = sorted({k for p in pairs for k in p["oasdiff"]})
        result["oasdiff_totals"] = {k: sum(p["oasdiff"].get(k, 0) for p in pairs) for k in kinds}
        result["oasdiff_total"] = sum(p["oasdiff_total"] for p in pairs)
    return result


def render(data) -> str:
    lines = [
        "# Census of breaking changes in real OpenAPI histories",
        "",
        "This file is written by `driftpatch census` from `results/census.json`. Do not edit the numbers by hand.",
        "",
        f"Run on {data['date']}. Samples per repo: {data['samples']}.",
        "",
        "## Method",
        "",
        "1. List each repo's tags with `git ls-remote --tags`. Nothing is cloned.",
        "2. Sort the tags by version and take evenly spaced ones, always the first and the last.",
        "3. Download the spec at each sampled tag from raw.githubusercontent.com into a local cache named by the SHA-256 of the URL.",
        "4. Diff each consecutive pair with the built-in differ. When oasdiff is installed, diff the pair with `oasdiff breaking` too.",
        "",
        "The built-in differ counts one change per field per schema, and credits every operation that uses the schema to that one change.",
        "oasdiff counts one finding per place it shows up, so one changed shared schema can give thousands of findings.",
        "The built-in differ skips `allOf`, `oneOf` and `anyOf` schemas. Stripe uses `anyOf` a lot, so the built-in counts are a floor.",
        "",
        "## Built-in differ, changes by kind",
        "",
        "| Repo | Tags listed | Pairs | Pairs with a breaking change | " + " | ".join(differ.KINDS) + " | Total |",
        "| --- | --- | --- | --- | " + " | ".join("---" for _ in differ.KINDS) + " | --- |",
    ]
    for res in data["repos"].values():
        cells = [str(res["builtin_totals"][k]) for k in differ.KINDS]
        lines.append(
            f"| {res['repo']} | {res['tags_listed']} | {len(res['pairs'])} | {res['pairs_with_breaking']} | "
            + " | ".join(cells)
            + f" | {res['builtin_total']} |"
        )
    if any("oasdiff_totals" in r for r in data["repos"].values()):
        lines += ["", "## oasdiff findings, mapped to the same kinds", "", "| Repo | Kind | Findings |", "| --- | --- | --- |"]
        for res in data["repos"].values():
            for k, n in sorted(res.get("oasdiff_totals", {}).items(), key=lambda kv: -kv[1]):
                lines.append(f"| {res['repo']} | {k} | {n} |")
            if "oasdiff_total" in res:
                lines.append(f"| {res['repo']} | all | {res['oasdiff_total']} |")
    lines += ["", "## Pairs", ""]
    for res in data["repos"].values():
        lines += [f"### {res['repo']}", "", "| From | To | Built-in | oasdiff |", "| --- | --- | --- | --- |"]
        for p in res["pairs"]:
            lines.append(f"| {p['from']} | {p['to']} | {p['builtin_total']} | {p.get('oasdiff_total', 'not run')} |")
        lines.append("")
    lines += [
        "## What this does not show",
        "",
        "- A sampled pair spans many releases, so a change that was added and then removed between two samples is not seen.",
        "- Both counts treat a new response enum value as breaking, because a strict client may reject it. Many clients ignore it.",
        "- Neither tool knows which changes were announced ahead or kept behind a version header. Stripe pins API versions per account.",
        "",
    ]
    return "\n".join(lines)


def run_census(root, repos=None, samples=20, cache=Path("data/census-cache"), lister=list_tags, fetch=http_get, use_oasdiff=None):
    root = Path(root)
    started = time.perf_counter()
    names = repos or list(REPOS)
    data = {"date": datetime.now(UTC).strftime("%Y-%m-%d"), "samples": samples, "repos": {}}
    for name in names:
        data["repos"][name] = census_repo(name, REPOS[name], samples, cache, lister, fetch, use_oasdiff)
        print(f"{name}: {data['repos'][name]['builtin_total']} built-in changes over {len(data['repos'][name]['pairs'])} pairs")
    data["seconds"] = round(time.perf_counter() - started, 1)
    (root / "results").mkdir(exist_ok=True)
    (root / "results" / "census.json").write_text(json.dumps(data, indent=2) + "\n")
    (root / "docs").mkdir(exist_ok=True)
    (root / "docs" / "CENSUS.md").write_text(render(data))
    return data
