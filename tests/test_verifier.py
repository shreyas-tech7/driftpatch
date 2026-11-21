"""The verifier and its pass rule."""

import shutil

from conftest import PY_CLIENT, ROOT, TS_CLIENT, V1, case

from driftpatch.patch import make_diff
from driftpatch.spec import load_spec
from driftpatch.verifier import baseline, detect_language, is_test_file, run_tests, verify


def new_spec(case_id):
    return load_spec(ROOT / case(case_id)["new_spec"])


def expected(case_id):
    return (ROOT / case(case_id)["expected_patch"]).read_text()


def edit(client, rel, old, new):
    text = (client / rel).read_text()
    assert old in text
    return make_diff({rel: text}, {rel: text.replace(old, new)})


def test_detect_language_and_test_files():
    assert detect_language(PY_CLIENT) == "python"
    assert detect_language(TS_CLIENT) == "ts"
    assert is_test_file("tests/test_client.py") and is_test_file("test/client.test.ts")
    assert not is_test_file("acme_client/client.py")


def test_correct_patch_passes_python():
    result = verify(new_spec("C001"), PY_CLIENT, expected("C001"))
    assert result.passed, result.reasons
    assert "tests.test_client::test_order_total" in result.fixed
    assert len(result.fixed) == 6  # every test that reads an Order
    assert result.regressions == []


def test_correct_patch_passes_ts():
    result = verify(new_spec("C002"), TS_CLIENT, expected("C002"))
    assert result.passed, result.reasons


def test_empty_patch_fails():
    assert verify(new_spec("C001"), PY_CLIENT, "").verdict == "fail"


def test_patch_that_leaves_a_failure_fails():
    """Broken case: the patch fixes nothing that the change broke."""
    diff = edit(PY_CLIENT, "acme_client/client.py", "timeout=5", "timeout=6")
    result = verify(new_spec("C005"), PY_CLIENT, diff)
    assert result.verdict == "fail"
    assert result.still_failing == ["tests.test_client::test_get_shipment"]


def test_regression_fails_even_when_the_target_test_passes():
    """Broken case: the patch fixes the shipment test but breaks the customer mapping."""
    rel = "acme_client/client.py"
    text = (PY_CLIENT / rel).read_text()
    patched = text.replace('tracking_number=data["tracking_number"]', 'tracking_number=data["tracking_code"]').replace(
        'name=data["name"]', 'name=data["full_name"]'
    )
    result = verify(new_spec("C005"), PY_CLIENT, make_diff({rel: text}, {rel: patched}))
    assert result.verdict == "fail"
    assert result.fixed == ["tests.test_client::test_get_shipment"]
    assert result.regressions == ["tests.test_client::test_get_customer"]


def test_patch_that_edits_tests_is_refused():
    diff = edit(PY_CLIENT, "tests/test_client.py", "assert order.total == 42.5", "assert True")
    result = verify(new_spec("C001"), PY_CLIENT, diff)
    assert result.verdict == "fail" and "edits test files" in result.reasons[0]


def test_patch_that_does_not_apply_is_refused():
    diff = "--- a/acme_client/client.py\n+++ b/acme_client/client.py\n@@ -1,1 +1,1 @@\n-no such line\n+x\n"
    result = verify(new_spec("C001"), PY_CLIENT, diff)
    assert result.verdict == "fail" and "does not apply" in result.reasons[0]


def test_nothing_to_fix_is_not_a_pass():
    diff = edit(PY_CLIENT, "acme_client/client.py", "timeout=5", "timeout=6")
    result = verify(load_spec(V1), PY_CLIENT, diff)
    assert result.verdict == "fail" and any("nothing to fix" in r for r in result.reasons)


def test_original_client_is_never_modified():
    before = (PY_CLIENT / "acme_client/client.py").read_text()
    verify(new_spec("C001"), PY_CLIENT, expected("C001"))
    assert (PY_CLIENT / "acme_client/client.py").read_text() == before


def test_timeout_is_reported(tmp_path):
    work = tmp_path / "client"
    shutil.copytree(PY_CLIENT, work)
    (work / "tests/test_slow.py").write_text("import time\n\ndef test_slow():\n    time.sleep(30)\n")
    run = run_tests(work, "http://127.0.0.1:9", "python", timeout=2)
    assert "timed out" in run.error


def test_baseline_counts_failures():
    run = baseline(new_spec("C031"), PY_CLIENT)
    assert run.failed == ["tests.test_client::test_cancel_order"]


def test_duplicate_test_names_are_kept_apart(tmp_path):
    from driftpatch.verifier import _parse_junit

    xml = tmp_path / "r.xml"
    xml.write_text(
        '<testsuites><testsuite><testcase classname="test" name="same"><failure/></testcase>'
        '<testcase classname="test" name="same"/></testsuite></testsuites>'
    )
    assert _parse_junit(xml) == {"test::same": False, "test::same#2": True}


def _tiny_client(tmp_path, body):
    client = tmp_path / "tiny"
    (client / "tests").mkdir(parents=True)
    (client / "pyproject.toml").write_text('[project]\nname = "tiny"\nversion = "0"\n')
    (client / "tests/test_env.py").write_text(body)
    return client


def test_secrets_do_not_reach_the_client_tests(tmp_path, monkeypatch):
    from driftpatch.verifier import run_tests

    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "x")
    monkeypatch.setenv("DB_PASSWORD", "x")
    monkeypatch.setenv("GROQ_API_KEY", "x")
    client = _tiny_client(
        tmp_path,
        "import os\n\ndef test_env():\n    assert not {'AWS_SECRET_ACCESS_KEY', 'DB_PASSWORD', 'GROQ_API_KEY'} & set(os.environ)\n",
    )
    run = run_tests(client, "http://127.0.0.1:9", "python", timeout=60)
    assert run.results and all(run.results.values()), run.output_tail


def test_planted_report_is_ignored(tmp_path):
    """Code under test cannot write a fake all-pass report where the verifier reads it."""
    from driftpatch.verifier import run_tests

    body = (
        "import os, pathlib\n\n"
        "def test_cheat():\n"
        "    pathlib.Path('.driftpatch-junit.xml').write_text('<testsuite><testcase name=\"x\"/></testsuite>')\n"
        "    assert False\n"
    )
    run = run_tests(_tiny_client(tmp_path, body), "http://127.0.0.1:9", "python", timeout=60)
    assert list(run.results.values()) == [False]
