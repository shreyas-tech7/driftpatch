"""The pipeline as an explicit state machine.

States run in this order: DIFF, FIND, PROPOSE, VERIFY, REPORT. Each state
returns an event. TRANSITIONS maps (state, event) to the next state. VERIFY is
the only branch that can end in a passing patch.

    DIFF    --changes-->      FIND     DIFF    --no_changes--> REPORT
    FIND    --sites-->        PROPOSE  FIND    --no_sites-->   REPORT
    PROPOSE --patch-->        VERIFY   PROPOSE --no_patch-->   REPORT
    VERIFY  --pass-->         REPORT   VERIFY  --fail-->       REPORT
    REPORT  --done-->         END
"""

from dataclasses import dataclass, field
from pathlib import Path

from . import differ, finder, oasdiff, verifier
from .spec import load_spec

DIFF, FIND, PROPOSE, VERIFY, REPORT, END = "DIFF", "FIND", "PROPOSE", "VERIFY", "REPORT", "END"

TRANSITIONS = {
    (DIFF, "changes"): FIND,
    (DIFF, "no_changes"): REPORT,
    (FIND, "sites"): PROPOSE,
    (FIND, "no_sites"): REPORT,
    (PROPOSE, "patch"): VERIFY,
    (PROPOSE, "no_patch"): REPORT,
    (VERIFY, "pass"): REPORT,
    (VERIFY, "fail"): REPORT,
    (REPORT, "done"): END,
}

# The final outcome, keyed by the event that led into REPORT.
OUTCOMES = {
    "no_changes": "no-breaking-changes",
    "no_sites": "no-affected-call-sites",
    "no_patch": "no-patch-proposed",
    "pass": "verified-patch",
    "fail": "patch-rejected",
}


class TransitionError(RuntimeError):
    pass


def next_state(state, event):
    try:
        return TRANSITIONS[(state, event)]
    except KeyError:
        raise TransitionError(f"no transition from {state} on {event!r}") from None


@dataclass
class Run:
    old_spec_path: str
    new_spec_path: str
    client_dir: str
    proposer: object
    timeout: int = verifier.DEFAULT_TIMEOUT
    use_oasdiff: bool = False
    state: str = DIFF
    history: list = field(default_factory=list)  # (state, event)
    old_spec: dict = None
    new_spec: dict = None
    language: str = ""
    changes: list = field(default_factory=list)
    oasdiff_findings: list = None
    sites: list = field(default_factory=list)
    proposal: object = None
    verification: object = None
    outcome: str = ""
    last_event: str = ""

    # ---- states

    def do_diff(self):
        self.old_spec = load_spec(self.old_spec_path)
        self.new_spec = load_spec(self.new_spec_path)
        self.changes = differ.diff_specs(self.old_spec, self.new_spec)
        if self.use_oasdiff and oasdiff.available():
            self.oasdiff_findings = oasdiff.breaking(self.old_spec_path, self.new_spec_path, timeout=self.timeout)
        return "changes" if self.changes else "no_changes"

    def do_find(self):
        self.language = verifier.detect_language(self.client_dir)
        self.sites = finder.find_sites(self.client_dir, self.changes, self.language)
        return "sites" if self.sites else "no_sites"

    def do_propose(self):
        self.proposal = self.proposer.propose(Path(self.client_dir), self.changes, self.sites, self.language)
        return "no_patch" if self.proposal.empty else "patch"

    def do_verify(self):
        self.verification = verifier.verify(self.new_spec, self.client_dir, self.proposal.diff, timeout=self.timeout)
        return "pass" if self.verification.passed else "fail"

    def do_report(self):
        self.outcome = OUTCOMES[self.last_event]
        return "done"

    HANDLERS = {DIFF: "do_diff", FIND: "do_find", PROPOSE: "do_propose", VERIFY: "do_verify", REPORT: "do_report"}

    def step(self):
        if self.state == END:
            raise TransitionError("the run has ended")
        event = getattr(self, self.HANDLERS[self.state])()
        self.history.append((self.state, event))
        if self.state != REPORT:
            self.last_event = event
        self.state = next_state(self.state, event)
        return event

    def run(self):
        while self.state != END:
            self.step()
        return self

    @property
    def verified(self) -> bool:
        return self.outcome == "verified-patch"
