"""The driftpatch command line: diff, find, patch, verify, run, bench, census, readme."""

import argparse
import json
import socket
import sys
from pathlib import Path

from . import __version__, differ, finder, guard, oasdiff, pipeline, report
from .proposer_llm import Endpoint, LLMProposer
from .proposer_rule import RuleProposer
from .spec import SpecError, load_spec
from .verifier import detect_language, verify


def _proposer(args):
    if args.proposer == "rule":
        return RuleProposer()
    endpoint = Endpoint(url=args.llm_url, model=args.llm_model, key_env=args.llm_key_env)
    return LLMProposer(mode=args.llm_mode, endpoint=endpoint, fixtures_dir=args.fixtures)


def _add_proposer_args(p):
    p.add_argument("--proposer", choices=["rule", "llm"], default="rule")
    p.add_argument("--llm-mode", choices=["replay", "record"], default="replay")
    p.add_argument("--llm-url", default=Endpoint.url)
    p.add_argument("--llm-model", default=Endpoint.model)
    p.add_argument("--llm-key-env", default=Endpoint.key_env, help="name of the environment variable that holds the key")
    p.add_argument("--fixtures", default="fixtures/llm")


def cmd_diff(args):
    old, new = load_spec(args.old), load_spec(args.new)
    changes = differ.diff_specs(old, new)
    found = None
    if args.engine in ("oasdiff", "both"):
        if not oasdiff.available():
            print("oasdiff is not installed. Using the built-in differ only.", file=sys.stderr)
        else:
            found = oasdiff.breaking(args.old, args.new)
    if args.json:
        print(json.dumps({"builtin": [c.to_dict() for c in changes], "oasdiff": found}, indent=2, default=str))
    else:
        print(f"{len(changes)} breaking change(s) found by the built-in differ")
        for c in changes:
            print(f"  [{c.kind}] {c.describe()}")
        if found is not None:
            print(f"{len(found)} finding(s) from oasdiff")
            for f in found:
                print(f"  [{f['id']}] {f['operation']} {f['path']}: {f['text']}")
    return 0


def cmd_find(args):
    changes = differ.diff_specs(load_spec(args.old), load_spec(args.new))
    sites = finder.find_sites(args.client, changes)
    if args.json:
        print(json.dumps([s.to_dict() for s in sites], indent=2))
    else:
        print(f"{len(sites)} call site(s) for {len(changes)} change(s)")
        for s in sites:
            print(f"  {s.file}:{s.line}:{s.col} {s.kind} {s.symbol!r} in {s.function}() <- {changes[s.change].kind}")
    return 0


def cmd_patch(args):
    changes = differ.diff_specs(load_spec(args.old), load_spec(args.new))
    language = detect_language(args.client)
    sites = finder.find_sites(args.client, changes, language)
    proposal = _proposer(args).propose(Path(args.client), changes, sites, language)
    for index, reason in proposal.declined:
        print(f"declined: {changes[index].describe()} ({reason})", file=sys.stderr)
    if args.out:
        Path(args.out).write_text(proposal.diff, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        sys.stdout.write(proposal.diff)
    return 0 if proposal.diff else 1


def cmd_verify(args):
    diff_text = Path(args.patch).read_text(encoding="utf-8")
    result = verify(load_spec(args.new), args.client, diff_text, timeout=args.timeout)
    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(f"verdict: {result.verdict}")
        print(f"before: {len(result.before_passed)} passed, {len(result.before_failed)} failed")
        print(f"after:  {len(result.after_passed)} passed, {len(result.after_failed)} failed")
        for r in result.reasons:
            print(f"  - {r}")
    return 0 if result.passed else 1


def _allowed_hosts(args):
    if args.proposer != "llm" or args.llm_mode != "record":
        return set()
    host = Endpoint(url=args.llm_url).host
    allowed = {host}
    try:
        allowed |= {info[4][0] for info in socket.getaddrinfo(host, 443)}
    except OSError:
        pass
    return allowed


def cmd_run(args):
    run = pipeline.Run(args.old, args.new, args.client, _proposer(args), timeout=args.timeout, use_oasdiff=args.oasdiff)
    if args.no_guard:
        run.run()
    else:
        with guard.guarded(_allowed_hosts(args)):
            run.run()
    paths = report.write_outputs(run, args.out)
    print(f"outcome: {run.outcome}")
    print(f"states: {' -> '.join(s for s, _ in run.history)} -> END")
    print(f"changes: {len(run.changes)}  call sites: {len(run.sites)}")
    if run.verification:
        v = run.verification
        print(
            f"verdict: {v.verdict}  before: {len(v.before_failed)} failing  after: {len(v.after_failed)} failing  regressions: {len(v.regressions)}"
        )
    for name, path in paths.items():
        print(f"wrote {name}: {path}")
    print("driftpatch did not push anything. Read the diff before you use it.")
    return 0 if run.outcome in ("verified-patch", "no-breaking-changes") else 1


def cmd_bench(args):
    from .bench import run_bench

    root = Path(args.root)

    def progress(row):
        mark = "PASS" if row["verified"] else "fail"
        print(f"  {row['id']} {row['language']:<6} {row['split']:<7} {mark} {row['outcome']} {row['error']}".rstrip())

    result = run_bench(root, args.proposer, args.split, args.llm_mode, args.timeout, progress)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2) + "\n")
    s = result["summary"]["all"]
    print(f"{args.proposer}: {s['verified']}/{s['cases']} verified, regressions {s['regressions']}, {result['meta']['seconds']}s")
    print(f"wrote {out}")
    return 0


def cmd_census(args):
    from .census import run_census

    run_census(Path(args.root), repos=args.repo, samples=args.samples, cache=Path(args.cache))
    return 0


def cmd_readme(args):
    from .readme import sync

    return sync(Path(args.root), check=args.check)


def build_parser():
    ap = argparse.ArgumentParser(
        prog="driftpatch", description="Find client code an OpenAPI change breaks, patch it, and verify the patch."
    )
    ap.add_argument("--version", action="version", version=f"driftpatch {__version__}")
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("diff", help="list breaking changes between two specs")
    p.add_argument("old")
    p.add_argument("new")
    p.add_argument("--engine", choices=["builtin", "oasdiff", "both"], default="builtin")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_diff)

    p = sub.add_parser("find", help="list the client call sites the changes affect")
    p.add_argument("old")
    p.add_argument("new")
    p.add_argument("client")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_find)

    p = sub.add_parser("patch", help="propose a patch (no verification)")
    p.add_argument("old")
    p.add_argument("new")
    p.add_argument("client")
    p.add_argument("--out", help="write the diff here instead of stdout")
    _add_proposer_args(p)
    p.set_defaults(func=cmd_patch)

    p = sub.add_parser("verify", help="run the client tests against a mock of the new spec, before and after a patch")
    p.add_argument("new")
    p.add_argument("client")
    p.add_argument("patch")
    p.add_argument("--timeout", type=int, default=120)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_verify)

    p = sub.add_parser("run", help="diff, find, propose, verify and report")
    p.add_argument("old")
    p.add_argument("new")
    p.add_argument("client")
    p.add_argument("--out", default="out/run")
    p.add_argument("--timeout", type=int, default=120)
    p.add_argument("--oasdiff", action="store_true", help="also list oasdiff findings in the report")
    p.add_argument("--no-guard", action="store_true", help="turn off the no-push and network guard")
    _add_proposer_args(p)
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("bench", help="run the frozen benchmark suite")
    p.add_argument("--proposer", choices=["rule", "oracle", "llm"], default="rule")
    p.add_argument("--llm-mode", choices=["replay", "record"], default="replay")
    p.add_argument("--split", choices=["all", "dev", "heldout"], default="all")
    p.add_argument("--root", default=".")
    p.add_argument("--out", default=None)
    p.add_argument("--timeout", type=int, default=120)
    p.set_defaults(func=cmd_bench)

    p = sub.add_parser("census", help="count breaking changes in real spec histories (uses the network)")
    p.add_argument("--repo", action="append", choices=["stripe", "github"], help="repeat to pick repos (default both)")
    p.add_argument("--samples", type=int, default=20)
    p.add_argument("--root", default=".")
    p.add_argument("--cache", default="data/census-cache")
    p.set_defaults(func=cmd_census)

    p = sub.add_parser("readme", help="write the README tables from the results files")
    p.add_argument("--root", default=".")
    p.add_argument("--check", action="store_true", help="fail if the README is out of date")
    p.set_defaults(func=cmd_readme)
    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)
    if getattr(args, "command", "") == "bench" and args.out is None:
        args.out = f"results/bench-{args.proposer}.json"
    try:
        return args.func(args)
    except (SpecError, FileNotFoundError, json.JSONDecodeError) as err:
        print(f"driftpatch: error: {err}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
