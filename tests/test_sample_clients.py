"""The sample clients pass their own tests against a mock of spec v1, and fail against v2."""

from conftest import PY_CLIENT, TS_CLIENT, V1, V2

from driftpatch.spec import load_spec
from driftpatch.verifier import baseline


def test_python_client_passes_on_v1():
    run = baseline(load_spec(V1), PY_CLIENT)
    assert run.error == ""
    assert len(run.results) == 10
    assert run.failed == []


def test_ts_client_passes_on_v1():
    run = baseline(load_spec(V1), TS_CLIENT)
    assert run.error == ""
    assert len(run.results) == 9
    assert run.failed == []


def test_v2_breaks_the_python_client():
    """Broken case: spec v2 renames Order.total, removes Order.note and adds a required parameter."""
    run = baseline(load_spec(V2), PY_CLIENT)
    assert len(run.failed) >= 3


def test_specs_are_openapi_3():
    for path in (V1, V2):
        assert load_spec(path)["openapi"].startswith("3.")
