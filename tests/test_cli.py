"""The command line, called in-process."""

from conftest import PY_CLIENT, TS_CLIENT, V1, V2

from driftpatch.cli import main


def test_version(capsys):
    try:
        main(["--version"])
    except SystemExit as err:
        assert err.code == 0
    assert "driftpatch" in capsys.readouterr().out


def test_diff_lists_changes(capsys):
    assert main(["diff", str(V1), str(V2)]) == 0
    out = capsys.readouterr().out
    assert "3 breaking change(s)" in out and "renamed-field" in out


def test_find_lists_sites(capsys):
    assert main(["find", str(V1), str(V2), str(TS_CLIENT)]) == 0
    assert "call site(s)" in capsys.readouterr().out


def test_patch_then_verify(tmp_path, capsys):
    diff = tmp_path / "fix.diff"
    assert main(["patch", str(V1), str(V2), str(PY_CLIENT), "--out", str(diff)]) == 0
    assert main(["verify", str(V2), str(PY_CLIENT), str(diff)]) == 0
    assert "verdict: pass" in capsys.readouterr().out


def test_run_writes_outputs(tmp_path, capsys):
    assert main(["run", str(V1), str(V2), str(PY_CLIENT), "--out", str(tmp_path / "run")]) == 0
    out = capsys.readouterr().out
    assert "outcome: verified-patch" in out and "did not push anything" in out


def test_bad_spec_is_a_clean_error(tmp_path, capsys):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    assert main(["diff", str(bad), str(V2)]) == 2
    assert "driftpatch: error" in capsys.readouterr().err


def test_missing_file_is_a_clean_error(tmp_path, capsys):
    assert main(["diff", str(tmp_path / "nope.json"), str(V2)]) == 2
