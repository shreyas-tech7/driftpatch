"""Write the three outputs of a run: the diff, the pull request text and the verification report.

driftpatch only writes files. It never pushes and never opens a pull request.
"""

import json
from pathlib import Path

from .patch import diff_size

HUMAN_GATE = (
    "driftpatch wrote this patch and did not push it or open a pull request. A person must read the diff and decide whether to merge it."
)


def pr_text(run) -> str:
    v = run.verification
    lines = ["# Update the client for the new API spec", ""]
    lines.append("## What changed in the API")
    lines.append("")
    if run.changes:
        lines += [f"- {c.describe()}" for c in run.changes]
    else:
        lines.append("- No breaking changes were found.")
    lines += ["", "## What this patch does", ""]
    p = run.proposal
    if p is None or p.empty:
        lines.append("- No patch was proposed.")
    else:
        lines.append(f"- Proposer: `{p.proposer}`. Files: {', '.join(f'`{f}`' for f in sorted(p.files))}.")
        lines.append(f"- Changed lines: {diff_size(p.diff)}.")
        for index in p.handled:
            lines.append(f"- Handles: {run.changes[index].describe()}")
    if p is not None and p.declined:
        lines += ["", "## Not handled", ""]
        lines += [f"- {run.changes[i].describe()} Reason: {reason}." for i, reason in p.declined]
    lines += ["", "## Verification", ""]
    if v is None:
        lines.append("- Not run.")
    else:
        lines.append(f"- Verdict: **{v.verdict}**.")
        lines.append(f"- Before the patch: {len(v.before_passed)} passed, {len(v.before_failed)} failed.")
        lines.append(f"- After the patch: {len(v.after_passed)} passed, {len(v.after_failed)} failed.")
        lines.append(f"- Fixed tests: {len(v.fixed)}. Regressions: {len(v.regressions)}.")
        lines += [f"- {r}" for r in v.reasons]
    lines += ["", "## Review", "", HUMAN_GATE, ""]
    return "\n".join(lines)


def verification_markdown(run) -> str:
    v = run.verification
    lines = [f"# Verification report: {run.outcome}", ""]
    lines.append(f"- Old spec: `{run.old_spec_path}`")
    lines.append(f"- New spec: `{run.new_spec_path}`")
    lines.append(f"- Client: `{run.client_dir}` ({run.language or 'unknown'})")
    lines.append(f"- States: {' -> '.join(s for s, _ in run.history)} -> END")
    lines.append(f"- Breaking changes: {len(run.changes)}. Call sites: {len(run.sites)}.")
    if run.oasdiff_findings is not None:
        lines.append(f"- oasdiff findings: {len(run.oasdiff_findings)}.")
    if v is not None:
        lines += ["", "| Test | Before | After |", "| --- | --- | --- |"]
        names = sorted(set(v.before_passed) | set(v.before_failed) | set(v.after_passed) | set(v.after_failed))
        for n in names:
            before = "pass" if n in v.before_passed else "fail"
            after = "pass" if n in v.after_passed else "fail"
            lines.append(f"| `{n}` | {before} | {after} |")
        lines += ["", f"Verdict: **{v.verdict}**."]
        lines += [f"- {r}" for r in v.reasons]
    lines.append("")
    return "\n".join(lines)


def summary(run) -> dict:
    p, v = run.proposal, run.verification
    return {
        "outcome": run.outcome,
        "verified": run.verified,
        "states": [s for s, _ in run.history],
        "events": [e for _, e in run.history],
        "language": run.language,
        "changes": [c.to_dict() for c in run.changes],
        "sites": [s.to_dict() for s in run.sites],
        "proposer": p.proposer if p else None,
        "declined": [[i, r] for i, r in (p.declined if p else [])],
        "patch_lines": diff_size(p.diff) if p and p.diff else 0,
        "tokens": p.tokens if p else 0,
        "verification": v.to_dict() if v else None,
        "oasdiff_findings": run.oasdiff_findings,
    }


def write_outputs(run, out_dir) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {
        "diff": out / "patch.diff",
        "pr": out / "PR.md",
        "report": out / "verification.md",
        "json": out / "verification.json",
    }
    paths["diff"].write_text(run.proposal.diff if run.proposal else "", encoding="utf-8")
    paths["pr"].write_text(pr_text(run), encoding="utf-8")
    paths["report"].write_text(verification_markdown(run), encoding="utf-8")
    paths["json"].write_text(json.dumps(summary(run), indent=2, default=str) + "\n", encoding="utf-8")
    return {k: str(v) for k, v in paths.items()}
