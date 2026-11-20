"""Write the README number blocks from the results files.

Each block sits between `<!-- driftpatch:NAME -->` and `<!-- /driftpatch:NAME -->`.
Nothing between the markers is typed by hand. `driftpatch readme --check` fails
when the README and the results files disagree.
"""

import json
import re
from pathlib import Path

from .differ import KINDS

PROPOSERS = [
    ("rule", "Rule baseline"),
    ("llm", "LLM (replay)"),
    ("oracle", "Answer key (sanity check)"),
]


def _load(root, name):
    path = Path(root) / "results" / name
    return json.loads(path.read_text()) if path.exists() else None


def _pct(x):
    return "n/a" if x is None else f"{100 * x:.1f}%"


def _ci(pair):
    return f"{100 * pair[0]:.1f} to {100 * pair[1]:.1f}"


def block_status(root):
    rule = _load(root, "bench-rule.json")
    timing = _load(root, "timing.json")
    census = _load(root, "census.json")
    if not rule:
        return "**Status:** v0.1.0-rc1. No benchmark results yet."
    s = rule["summary"]["all"]
    parts = [
        f"**Status:** v0.1.0-rc1, a release candidate. The rule baseline fixes {s['verified']} of {s['cases']} frozen cases with {s['regressions']} regressions"
    ]
    if timing:
        parts.append(f"and the suite runs in {timing['seconds']:.0f} s on {timing['cores']} cores")
    text = " ".join(parts) + "."
    if census:
        repos = census["repos"].values()
        text += f" The census covers {sum(len(r['pairs']) for r in repos)} release pairs of {len(census['repos'])} real APIs."
    return text


def block_results(root):
    lines = [
        "| Proposer | Cases verified | 95% interval | Test pass rate after | 95% interval | Regressions | Median patch lines | Tokens | Held-out verified |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for key, label in PROPOSERS:
        data = _load(root, f"bench-{key}.json")
        if not data or data["meta"]["status"] != "ok":
            lines.append(f"| {label} | not run | | | | | | | |")
            continue
        a, h = data["summary"]["all"], data["summary"]["heldout"]
        lines.append(
            f"| {label} | {a['verified']} of {a['cases']} | {_ci(a['verified_ci95'])} | {_pct(a['test_pass_rate'])} | {_ci(a['test_pass_rate_ci95'])} "
            f"| {a['regressions']} | {a['patch_lines_median']:g} | {a['tokens']} | {h['verified']} of {h['cases']} |"
        )
    rule = _load(root, "bench-rule.json")
    if rule:
        m = rule["meta"]
        lines += [
            "",
            f"Run on {m['date']}, {m['cpu']}, Python {m['python']}. Seed: {m['seed']} Frozen files checked: {m['frozen_files_checked']}.",
        ]
    return "\n".join(lines)


def block_kinds(root):
    rule = _load(root, "bench-rule.json")
    if not rule:
        return "No results yet."
    by_kind = {}
    for row in rule["cases"]:
        for k in row["kinds"]:
            n, v = by_kind.get(k, (0, 0))
            by_kind[k] = (n + 1, v + int(row["verified"]))
    lines = ["| Change kind | Cases with it | Fixed by the rule baseline |", "| --- | --- | --- |"]
    for k in KINDS:
        if k in by_kind:
            n, v = by_kind[k]
            lines.append(f"| {k} | {n} | {v} |")
    return "\n".join(lines)


def block_cost(root):
    lines = ["| Proposer | Money per case | Tokens per case | Seconds per case |", "| --- | --- | --- | --- |"]
    for key, label in PROPOSERS:
        data = _load(root, f"bench-{key}.json")
        if not data or data["meta"]["status"] != "ok":
            lines.append(f"| {label} | not run | not run | not run |")
            continue
        n = data["summary"]["all"]["cases"] or 1
        money = "$0 (no model)" if key in ("rule", "oracle") else "see tokens"
        lines.append(f"| {label} | {money} | {data['summary']['all']['tokens'] / n:.0f} | {data['meta']['seconds'] / n:.1f} |")
    timing = _load(root, "timing.json")
    if timing:
        lines += [
            "",
            f"The full rule run took {timing['seconds']:.1f} s on {timing['cores']} cores ({timing['cpu']}) on {timing['date']}, against a limit of {timing['limit']:.0f} s.",
        ]
    return "\n".join(lines)


def block_census(root):
    census = _load(root, "census.json")
    if not census:
        return "Census not run yet."
    lines = [
        "| API | Release pairs | Pairs with a breaking change | " + " | ".join(KINDS) + " |",
        "| --- | --- | --- | " + " | ".join("---" for _ in KINDS) + " |",
    ]
    for r in census["repos"].values():
        lines.append(
            f"| {r['repo']} | {len(r['pairs'])} | {r['pairs_with_breaking']} | "
            + " | ".join(str(r["builtin_totals"][k]) for k in KINDS)
            + " |"
        )
    lines += ["", f"Built-in differ counts from {census['date']}. Method and the oasdiff counts are in [docs/CENSUS.md](docs/CENSUS.md)."]
    return "\n".join(lines)


BLOCKS = {"status": block_status, "results": block_results, "kinds": block_kinds, "cost": block_cost, "census": block_census}


def render(text, root):
    for name, fn in BLOCKS.items():
        pattern = re.compile(rf"(<!-- driftpatch:{name} -->)\n(?:(.*?)\n)?(<!-- /driftpatch:{name} -->)", re.S)
        if not pattern.search(text):
            raise ValueError(f"README has no driftpatch:{name} block")
        body = fn(root)
        text = pattern.sub(lambda m, body=body: f"{m.group(1)}\n{body}\n{m.group(3)}", text)
    return text


def sync(root, check=False) -> int:
    path = Path(root) / "README.md"
    old = path.read_text()
    new = render(old, root)
    if check:
        if new != old:
            print("README.md is out of date. Run `driftpatch readme`.")
            return 1
        print("README.md matches the results files.")
        return 0
    path.write_text(new)
    print("README.md updated from results/.")
    return 0
