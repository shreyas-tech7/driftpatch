"""The run outputs: diff, PR text and verification report."""

import json

from conftest import PY_CLIENT, V1, V2

from driftpatch.pipeline import Run
from driftpatch.proposer_rule import RuleProposer
from driftpatch.report import HUMAN_GATE, pr_text, verification_markdown, write_outputs


def done_run():
    return Run(str(V1), str(V2), str(PY_CLIENT), RuleProposer()).run()


def test_outputs_are_written(tmp_path):
    run = done_run()
    paths = write_outputs(run, tmp_path / "out")
    assert set(paths) == {"diff", "pr", "report", "json"}
    data = json.loads((tmp_path / "out/verification.json").read_text())
    assert data["outcome"] == "verified-patch" and data["verified"]
    assert (tmp_path / "out/patch.diff").read_text().startswith("--- a/")


def test_pr_text_names_every_change_and_the_human_gate():
    run = done_run()
    text = pr_text(run)
    for c in run.changes:
        assert c.describe() in text
    assert HUMAN_GATE in text
    assert "Regressions: 0" in text


def test_report_has_a_row_per_test():
    run = done_run()
    md = verification_markdown(run)
    names = set(run.verification.after_passed) | set(run.verification.after_failed)
    assert all(f"`{n}`" in md for n in names)
