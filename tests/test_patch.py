"""Diff writing and the strict diff applier."""

import pytest

from driftpatch.patch import PatchError, apply_diff, diff_size, files_in_diff, make_diff, parse_diff, safe_relpath


def test_round_trip(tmp_path):
    (tmp_path / "a.py").write_text("one\ntwo\nthree\n")
    diff = make_diff({"a.py": "one\ntwo\nthree\n"}, {"a.py": "one\n2\nthree\nfour\n"})
    assert files_in_diff(diff) == ["a.py"]
    assert diff_size(diff) == 3
    assert apply_diff(diff, tmp_path) == {"a.py": "one\n2\nthree\nfour\n"}


def test_context_mismatch_is_refused(tmp_path):
    """Broken case: the file changed after the patch was made, so the context no longer matches."""
    diff = make_diff({"a.py": "one\ntwo\n"}, {"a.py": "one\nTWO\n"})
    (tmp_path / "a.py").write_text("uno\ntwo\n")
    with pytest.raises(PatchError):
        apply_diff(diff, tmp_path)


def test_missing_newline_at_end(tmp_path):
    (tmp_path / "a.ts").write_text("x")
    diff = make_diff({"a.ts": "x"}, {"a.ts": "y"})
    assert apply_diff(diff, tmp_path) == {"a.ts": "y"}


@pytest.mark.parametrize("rel", ["../evil.py", "/etc/passwd", "a/../../b", "C:/x", "a\\b"])
def test_unsafe_paths(rel):
    with pytest.raises(PatchError):
        safe_relpath(rel)


def test_unsafe_path_inside_a_diff():
    diff = "--- a/../x\n+++ b/../x\n@@ -1 +1 @@\n-a\n+b\n"
    with pytest.raises(PatchError):
        parse_diff(diff)


def test_garbage_hunk_line():
    with pytest.raises(PatchError):
        parse_diff("--- a/x\n+++ b/x\n@@ -1 +1 @@\n?a\n")


def test_removed_line_that_looks_like_a_header():
    from driftpatch.patch import apply_to_text, make_diff, parse_diff

    old = "a\n-- comment\nb\n"
    new = "a\nb\n"
    diff = make_diff({"f.sql": old}, {"f.sql": new})
    assert "\n--- comment\n" in diff
    assert apply_to_text(old, parse_diff(diff)["f.sql"]) == new


def test_form_feed_is_not_a_line_break():
    from driftpatch.patch import apply_to_text, make_diff, parse_diff

    old = "x = 1\x0c\ny = 2\n"
    new = "x = 1\x0c\ny = 3\n"
    diff = make_diff({"f.py": old}, {"f.py": new})
    assert apply_to_text(old, parse_diff(diff)["f.py"]) == new
