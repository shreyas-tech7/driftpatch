"""The README number blocks come from results/, and the check catches drift."""

import json
import shutil

import pytest
from conftest import ROOT

from driftpatch import readme

BLOCKS = list(readme.BLOCKS)


def copy_repo(tmp_path):
    dest = tmp_path / "repo"
    dest.mkdir()
    shutil.copy(ROOT / "README.md", dest / "README.md")
    shutil.copytree(ROOT / "results", dest / "results")
    return dest


def test_readme_matches_results():
    assert readme.sync(ROOT, check=True) == 0


def test_every_block_is_present():
    text = (ROOT / "README.md").read_text()
    for name in BLOCKS:
        assert f"<!-- driftpatch:{name} -->" in text and f"<!-- /driftpatch:{name} -->" in text


def test_hand_edited_number_is_caught(tmp_path):
    repo = copy_repo(tmp_path)
    path = repo / "README.md"
    text = path.read_text()
    start = text.index("<!-- driftpatch:results -->")
    path.write_text(text[:start] + text[start:].replace(" of 36 ", " of 37 ", 1))
    assert readme.sync(repo, check=True) == 1


def test_numbers_follow_the_results_file(tmp_path):
    repo = copy_repo(tmp_path)
    data = json.loads((repo / "results/bench-rule.json").read_text())
    data["summary"]["all"]["regressions"] = 99
    (repo / "results/bench-rule.json").write_text(json.dumps(data))
    assert readme.sync(repo, check=True) == 1
    readme.sync(repo)
    assert "| 99 |" in (repo / "README.md").read_text()


def test_missing_block_is_an_error(tmp_path):
    repo = copy_repo(tmp_path)
    (repo / "README.md").write_text("# empty\n")
    with pytest.raises(ValueError):
        readme.sync(repo, check=True)


def test_llm_row_says_not_run_without_results(tmp_path):
    repo = copy_repo(tmp_path)
    (repo / "results/bench-llm.json").unlink(missing_ok=True)
    assert "| LLM (replay) | not run |" in readme.block_results(repo)
