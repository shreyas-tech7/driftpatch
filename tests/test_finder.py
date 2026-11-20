"""Call-site finders for Python (ast) and TypeScript (patterns)."""

import json

from conftest import PY_CLIENT, ROOT, TS_CLIENT, V1

from driftpatch.differ import diff_specs
from driftpatch.finder import find_sites, match_brace, source_files
from driftpatch.spec import load_spec


def sites_for(case_id, client):
    new = load_spec(ROOT / "bench/cases" / case_id / "new.json")
    changes = diff_specs(load_spec(V1), new)
    return changes, find_sites(client, changes)


def test_python_skips_test_files():
    assert source_files(PY_CLIENT, "python") == ["acme_client/__init__.py", "acme_client/client.py"]


def test_python_response_rename_found_in_helper():
    changes, sites = sites_for("C001", PY_CLIENT)
    assert [(s.kind, s.symbol, s.function) for s in sites] == [("response-key", "total", "from_api")]


def test_python_scope_keeps_other_schemas_out():
    """Broken case: a whole-file search would also flag Order.status for a Refund.status rename."""
    _, sites = sites_for("C007", PY_CLIENT)
    assert [(s.function, s.symbol) for s in sites] == [("create_refund", "status")]


def test_python_request_key_found():
    _, sites = sites_for("C009", PY_CLIENT)
    assert [(s.kind, s.function) for s in sites] == [("request-key", "create_order")]


def test_python_endpoint_call_for_new_parameter():
    _, sites = sites_for("C016", PY_CLIENT)
    assert [(s.kind, s.function) for s in sites] == [("endpoint-call", "list_items")]


def test_python_enum_literal_in_a_caller():
    changes, sites = sites_for("C030", PY_CLIENT)
    assert len(changes) == 2  # the query enum and the Order.status enum
    assert {(s.kind, s.symbol, s.function) for s in sites} == {("enum-literal", "cancelled", "list_cancelled_orders")}


def test_python_removed_endpoint():
    _, sites = sites_for("C031", PY_CLIENT)
    assert [(s.kind, s.function) for s in sites] == [("endpoint-call", "cancel_order")]


def test_ts_skips_test_files():
    assert source_files(TS_CLIENT, "ts") == ["src/client.ts"]


def test_ts_response_rename_found_in_helper():
    _, sites = sites_for("C002", TS_CLIENT)
    assert [(s.kind, s.function) for s in sites] == [("response-key", "toOrder")]


def test_ts_request_key_scoped_to_the_caller():
    """Broken case: `note:` also appears in toOrder and in the Order interface."""
    _, sites = sites_for("C010", TS_CLIENT)
    assert [(s.kind, s.function) for s in sites] == [("request-key", "createOrder")]


def test_ts_enum_literal_in_a_caller():
    _, sites = sites_for("C029", TS_CLIENT)
    assert [(s.kind, s.symbol, s.function) for s in sites] == [("enum-literal", "fraud", "cancelForFraud")]


def test_ts_template_literal_endpoint():
    _, sites = sites_for("C032", TS_CLIENT)
    assert [(s.kind, s.function) for s in sites] == [("endpoint-call", "listItems")]


def test_ts_brace_matcher_skips_strings():
    text = 'f() { const s = "}"; return `x${1}`; }'
    assert match_brace(text, text.index("{")) == len(text)


def test_every_case_has_sites():
    for path in sorted((ROOT / "bench/cases").glob("C*/case.json")):
        case = json.loads(path.read_text())
        changes = diff_specs(load_spec(ROOT / case["old_spec"]), load_spec(ROOT / case["new_spec"]))
        assert changes, case["id"]
        assert find_sites(ROOT / case["client"], changes), case["id"]
