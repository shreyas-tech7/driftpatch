"""The LLM proposer: replay mode, record mode with a fake transport, and answer checks.

The answers here are hand-written test fixtures, not model output.
"""

import json

import pytest
from conftest import PY_CLIENT, ROOT, V1, case

from driftpatch.differ import diff_specs
from driftpatch.finder import find_sites
from driftpatch.patch import PatchError
from driftpatch.pipeline import Run
from driftpatch.proposer_llm import Endpoint, LLMProposer, RecordError, ReplayMissing, build_prompt, parse_answer, prompt_sha
from driftpatch.spec import load_spec

CASE = "C031"  # the cancel endpoint moved: the rule baseline cannot fix it


def setup():
    c = case(CASE)
    changes = diff_specs(load_spec(V1), load_spec(ROOT / c["new_spec"]))
    sites = find_sites(PY_CLIENT, changes, "python")
    return changes, sites


def fixed_answer():
    text = (PY_CLIENT / "acme_client/client.py").read_text()
    new = text.replace('f"/orders/{order_id}/cancel"', 'f"/orders/{order_id}/cancellation"')
    return f'<file path="acme_client/client.py">\n{new}</file>\n'


def write_fixture(tmp_path, answer, usage=None):
    changes, sites = setup()
    files = {"acme_client/client.py": (PY_CLIENT / "acme_client/client.py").read_text()}
    prompt = build_prompt(changes, sites, files)
    model = Endpoint().model
    folder = tmp_path / model
    folder.mkdir(parents=True)
    record = {"answer": answer, "usage": usage or {"prompt_tokens": 1000, "completion_tokens": 900}}
    (folder / f"{prompt_sha(prompt, model)}.json").write_text(json.dumps(record))
    return tmp_path


def test_replay_produces_a_verified_patch(tmp_path):
    fixtures = write_fixture(tmp_path, fixed_answer())
    run = Run(str(V1), str(ROOT / case(CASE)["new_spec"]), str(PY_CLIENT), LLMProposer("replay", fixtures_dir=fixtures)).run()
    assert run.verified
    assert run.proposal.tokens == 1900


def test_replay_without_a_recording_is_an_error(tmp_path):
    changes, sites = setup()
    with pytest.raises(ReplayMissing):
        LLMProposer("replay", fixtures_dir=tmp_path).propose(PY_CLIENT, changes, sites, "python")


def test_answer_that_edits_a_test_file_is_refused():
    with pytest.raises(PatchError):
        parse_answer('<file path="tests/test_client.py">x</file>', {"tests/test_client.py"})


def test_answer_with_path_traversal_is_refused():
    with pytest.raises(PatchError):
        parse_answer('<file path="../../etc/x">x</file>', {"acme_client/client.py"})


def test_answer_for_a_file_it_was_not_given_is_refused():
    with pytest.raises(PatchError):
        parse_answer('<file path="acme_client/other.py">x</file>', {"acme_client/client.py"})


def test_bad_answer_gives_an_empty_proposal(tmp_path):
    fixtures = write_fixture(tmp_path, '<file path="tests/test_client.py">x</file>')
    changes, sites = setup()
    proposal = LLMProposer("replay", fixtures_dir=fixtures).propose(PY_CLIENT, changes, sites, "python")
    assert proposal.empty and proposal.notes


def test_record_mode_backs_off_on_429_and_saves(tmp_path, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-not-a-key")
    calls, sleeps = [], []
    answer = fixed_answer()

    def transport(url, payload, key):
        calls.append(key)
        if len(calls) < 3:
            return 429, "slow down"
        body = {"choices": [{"message": {"content": answer}}], "usage": {"prompt_tokens": 5, "completion_tokens": 7}}
        return 200, json.dumps(body)

    changes, sites = setup()
    proposer = LLMProposer("record", fixtures_dir=tmp_path, transport=transport, sleep=sleeps.append)
    proposal = proposer.propose(PY_CLIENT, changes, sites, "python")
    assert sleeps == [2.0, 4.0]
    assert proposal.tokens == 12 and not proposal.empty
    saved = list((tmp_path / Endpoint().model).glob("*.json"))
    assert len(saved) == 1 and "test-not-a-key" not in saved[0].read_text()


def test_record_mode_403_is_blocked(tmp_path):
    changes, sites = setup()
    proposer = LLMProposer("record", fixtures_dir=tmp_path, transport=lambda u, p, k: (403, "no"))
    with pytest.raises(RecordError):
        proposer.propose(PY_CLIENT, changes, sites, "python")


def test_endpoint_must_be_https():
    with pytest.raises(ValueError):
        LLMProposer("record", endpoint=Endpoint(url="http://api.example.org/v1"))


def test_prompt_is_stable():
    changes, sites = setup()
    files = {"acme_client/client.py": (PY_CLIENT / "acme_client/client.py").read_text()}
    assert build_prompt(changes, sites, files) == build_prompt(changes, sites, files)
    assert "cancel" in build_prompt(changes, sites, files)
