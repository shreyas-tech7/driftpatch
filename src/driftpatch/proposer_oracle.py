"""The oracle proposer replays the case's known correct patch.

It is not a real proposer. It checks the benchmark: a case is valid only if
its own answer key passes the verifier.
"""

from pathlib import Path

from .patch import apply_diff
from .proposer_rule import Proposal


class OracleProposer:
    name = "oracle"

    def __init__(self, diff_text: str):
        self.diff_text = diff_text

    def propose(self, client_dir, changes, sites, language) -> Proposal:
        files = apply_diff(self.diff_text, Path(client_dir))
        return Proposal(self.name, files=files, diff=self.diff_text, handled=list(range(len(changes))))
