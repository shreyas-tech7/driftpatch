"""The pipeline state machine: every transition has a test."""

import pytest
from conftest import PY_CLIENT, ROOT, V1, V2, case

from driftpatch import pipeline
from driftpatch.pipeline import DIFF, END, FIND, PROPOSE, REPORT, TRANSITIONS, VERIFY, Run, TransitionError, next_state
from driftpatch.proposer_oracle import OracleProposer
from driftpatch.proposer_rule import Proposal, RuleProposer


class FixedProposer:
    def __init__(self, diff):
        self.diff = diff

    def propose(self, client_dir, changes, sites, language):
        return Proposal("fixed", diff=self.diff, files={"x": "y"} if self.diff else {})


def new(case_id):
    return str(ROOT / case(case_id)["new_spec"])


def states(run):
    return [s for s, _ in run.history]


def test_transition_table_is_complete():
    assert set(TRANSITIONS.values()) <= {FIND, PROPOSE, VERIFY, REPORT, END}
    assert {s for s, _ in TRANSITIONS} == {DIFF, FIND, PROPOSE, VERIFY, REPORT}


def test_unknown_transition_raises():
    with pytest.raises(TransitionError):
        next_state(VERIFY, "maybe")


def test_diff_no_changes_goes_to_report():
    run = Run(str(V1), str(V1), str(PY_CLIENT), RuleProposer()).run()
    assert run.history == [(DIFF, "no_changes"), (REPORT, "done")]
    assert run.outcome == "no-breaking-changes"


def test_find_no_sites_goes_to_report(tmp_path):
    client = tmp_path / "client"
    (client / "tests").mkdir(parents=True)
    (client / "pyproject.toml").write_text("[project]\nname='x'\n")
    (client / "app.py").write_text("def hello():\n    return 1\n")
    run = Run(str(V1), str(V2), str(client), RuleProposer()).run()
    assert states(run) == [DIFF, FIND, REPORT]
    assert run.outcome == "no-affected-call-sites"


def test_propose_no_patch_goes_to_report():
    run = Run(str(V1), new("C031"), str(PY_CLIENT), RuleProposer()).run()
    assert run.history[:3] == [(DIFF, "changes"), (FIND, "sites"), (PROPOSE, "no_patch")]
    assert run.outcome == "no-patch-proposed"


def test_verify_pass_branch():
    run = Run(str(V1), str(V2), str(PY_CLIENT), RuleProposer()).run()
    assert run.history == [(DIFF, "changes"), (FIND, "sites"), (PROPOSE, "patch"), (VERIFY, "pass"), (REPORT, "done")]
    assert run.verified


def test_verify_fail_branch():
    diff = (ROOT / case("C001")["expected_patch"]).read_text()  # the answer to another case
    run = Run(str(V1), new("C005"), str(PY_CLIENT), FixedProposer(diff)).run()
    assert run.history[-2:] == [(VERIFY, "fail"), (REPORT, "done")]
    assert run.outcome == "patch-rejected"


def test_oracle_passes_its_own_case():
    c = case("C031")
    run = Run(str(V1), new("C031"), str(PY_CLIENT), OracleProposer((ROOT / c["expected_patch"]).read_text())).run()
    assert run.verified


def test_step_after_end_raises():
    run = Run(str(V1), str(V1), str(PY_CLIENT), RuleProposer()).run()
    assert run.state == END
    with pytest.raises(TransitionError):
        run.step()


def test_outcomes_cover_every_event_into_report():
    into_report = {event for (_, event), target in TRANSITIONS.items() if target == REPORT}
    assert into_report == set(pipeline.OUTCOMES)
