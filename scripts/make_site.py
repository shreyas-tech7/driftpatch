"""Write docs/index.html, a static results page that opens from disk with no server.
Every number comes from the results files. Run: .venv/bin/python scripts/make_site.py
Add --check to compare without writing."""

import html
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from driftpatch.differ import KINDS  # noqa: E402

LABELS = [("rule", "Rule baseline"), ("llm", "LLM (replay)"), ("oracle", "Answer key (sanity check)")]


def load(rel):
    path = ROOT / rel
    return json.loads(path.read_text()) if path.exists() else None


def ci(pair):
    return f"<small>({100 * pair[0]:.1f} to {100 * pair[1]:.1f})</small>"


def render() -> str:
    rows = ""
    for key, label in LABELS:
        d = load(f"results/bench-{key}.json")
        if not d or d["meta"]["status"] != "ok":
            rows += f"<tr><th scope=row>{label}</th><td colspan=5>not run</td></tr>"
            continue
        a = d["summary"]["all"]
        rows += (
            f"<tr><th scope=row>{label}</th><td>{a['verified']} of {a['cases']} {ci(a['verified_ci95'])}</td>"
            f"<td>{100 * a['test_pass_rate']:.1f}% {ci(a['test_pass_rate_ci95'])}</td><td>{a['regressions']}</td>"
            f"<td>{a['patch_lines_median']}</td><td>{a['tokens']}</td></tr>"
        )
    rule = load("results/bench-rule.json")
    cases = "".join(
        f"<tr><td>{c['id']}</td><td>{html.escape(c['title'])}</td><td>{c['language']}</td><td>{c['split']}</td>"
        f"<td>{'verified' if c['verified'] else html.escape(c['outcome'])}</td></tr>"
        for c in rule["cases"]
    )
    census = load("results/census.json")
    cen = "".join(
        f"<tr><th scope=row>{html.escape(r['repo'])}</th><td>{len(r['pairs'])}</td><td>{r['pairs_with_breaking']}</td>"
        + "".join(f"<td>{r['builtin_totals'][k]}</td>" for k in KINDS)
        + "</tr>"
        for r in census["repos"].values()
    )
    kind_heads = "".join(f"<th>{k}</th>" for k in KINDS)
    m = rule["meta"]
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>driftpatch results</title>
<style>
:root {{ --bg: #f6f7fa; --fg: #182030; --muted: #5a6478; --line: #d4d9e2; --accent: #1f7a62; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg: #141a28; --fg: #e8ecf4; --muted: #a0aabe;
  --line: #313a4e; --accent: #6ec4aa; }} }}
body {{ background: var(--bg); color: var(--fg); font: 16px/1.5 system-ui, sans-serif; margin: 0 auto;
  max-width: 980px; padding: 24px 16px; }}
table {{ border-collapse: collapse; width: 100%; display: block; overflow-x: auto; }}
th, td {{ border-bottom: 1px solid var(--line); padding: 6px 8px; text-align: left; vertical-align: top; }}
small, .muted {{ color: var(--muted); }}
a {{ color: var(--accent); }}
</style>
</head>
<body>
<h1>driftpatch</h1>
<p>driftpatch reads two versions of an OpenAPI spec, finds the client code each breaking change hits, proposes a
patch and verifies it by running the client's own tests against a mock of the new spec. It never pushes.</p>
<h2>Benchmark</h2>
<table><thead><tr><th>Proposer</th><th>Cases verified (95% interval)</th><th>Test pass rate after (95% interval)</th>
<th>Regressions</th><th>Median patch lines</th><th>Tokens</th></tr></thead><tbody>{rows}</tbody></table>
<p class="muted">Synthetic suite built from one invented API. Run {m["date"]} on {html.escape(m["cpu"])}.
{html.escape(m["seed"])}</p>
<h2>Census of real spec histories</h2>
<table><thead><tr><th>API</th><th>Release pairs</th><th>Pairs with a breaking change</th>{kind_heads}</tr></thead>
<tbody>{cen}</tbody></table>
<p class="muted">Built-in differ counts from {census["date"]}. The method is in docs/CENSUS.md.</p>
<h2>Every case, rule baseline</h2>
<table><thead><tr><th>Case</th><th>Change</th><th>Client</th><th>Split</th><th>Result</th></tr></thead>
<tbody>{cases}</tbody></table>
<p class="muted">Written by scripts/make_site.py from the results folder. See the <a href="../README.md">README</a>.</p>
</body>
</html>
"""


def main(argv) -> int:
    out = ROOT / "docs" / "index.html"
    page = render()
    if "--check" in argv:
        ok = out.exists() and out.read_text(encoding="utf-8") == page
        print("docs/index.html matches the results files" if ok else "docs/index.html is stale: run scripts/make_site.py")
        return 0 if ok else 1
    out.write_text(page, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
