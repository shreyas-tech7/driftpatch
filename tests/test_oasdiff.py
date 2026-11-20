"""The oasdiff adapter. The id mapping is tested without the binary. The real run is skipped if oasdiff is missing."""

import os
import stat

import pytest
from conftest import V1, V2

from driftpatch import differ, oasdiff


@pytest.mark.parametrize(
    "check_id,kind",
    [
        ("api-path-removed-without-deprecation", differ.REMOVED_ENDPOINT),
        ("new-required-request-parameter", differ.NEW_REQUIRED_PARAMETER),
        ("response-property-enum-value-removed", differ.CHANGED_ENUM),
        ("response-property-type-changed", differ.CHANGED_TYPE),
        ("response-required-property-removed", differ.REMOVED_FIELD),
        ("something-new", "other"),
    ],
)
def test_kind_for(check_id, kind):
    assert oasdiff.kind_for(check_id) == kind


def test_fake_binary_output_is_parsed(tmp_path, monkeypatch):
    exe = tmp_path / "oasdiff"
    exe.write_text(
        '#!/bin/sh\necho \'[{"id":"api-path-removed-without-deprecation","level":3,"operation":"GET","path":"/x","text":"gone"}]\'\nexit 1\n'
    )
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ['PATH']}")
    found = oasdiff.breaking(V1, V2)
    assert found == [
        {
            "id": "api-path-removed-without-deprecation",
            "kind": differ.REMOVED_ENDPOINT,
            "level": 3,
            "operation": "GET",
            "path": "/x",
            "text": "gone",
        }
    ]


def test_failing_binary_raises(tmp_path, monkeypatch):
    exe = tmp_path / "oasdiff"
    exe.write_text("#!/bin/sh\necho boom >&2\nexit 3\n")
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ['PATH']}")
    with pytest.raises(oasdiff.OasdiffError):
        oasdiff.breaking(V1, V2)


@pytest.mark.skipif(not oasdiff.available(), reason="oasdiff is not installed")
def test_real_oasdiff_sees_the_removed_field():
    found = oasdiff.breaking(V1, V2)
    assert found, "oasdiff found nothing"
    assert any(f["kind"] in (differ.REMOVED_FIELD, differ.NEW_REQUIRED_PARAMETER) for f in found)
