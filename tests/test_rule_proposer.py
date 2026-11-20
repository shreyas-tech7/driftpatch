"""The rule-based baseline."""

from conftest import PY_CLIENT, ROOT, TS_CLIENT, V1, case

from driftpatch.differ import diff_specs
from driftpatch.finder import find_sites
from driftpatch.proposer_rule import RuleProposer
from driftpatch.spec import load_spec


def propose(case_id):
    c = case(case_id)
    client = ROOT / c["client"]
    changes = diff_specs(load_spec(V1), load_spec(ROOT / c["new_spec"]))
    lang = c["language"]
    proposal = RuleProposer().propose(client, changes, find_sites(client, changes, lang), lang)
    return proposal


def changed_lines(proposal):
    return [line for line in proposal.diff.splitlines() if line[:1] in "+-" and line[:3] not in ("+++", "---")]


def test_python_response_rename():
    assert changed_lines(propose("C001")) == ['-            total=data["total"],', '+            total=data["total_amount"],']


def test_python_request_rename():
    assert changed_lines(propose("C009"))[1] == '+            "email": customer_email,'


def test_ts_response_rename():
    assert changed_lines(propose("C002"))[1] == "+    total: raw.total_amount,"


def test_ts_request_rename_leaves_the_model_alone():
    lines = changed_lines(propose("C010"))
    assert lines == ["-      note: note,", "+      comment: note,"]


def test_python_new_param_into_existing_dict():
    assert changed_lines(propose("C014"))[1] == '+        params = {"status": status, "limit": limit, "currency": "USD"}'


def test_python_new_param_as_new_keyword():
    assert changed_lines(propose("C016"))[1].endswith('f"/orders/{order_id}/items", params={"expand": "none"})')


def test_ts_new_param_into_query_variable():
    assert changed_lines(propose("C015"))[1] == '+    const query = { status: status, limit: String(limit), currency: "USD" };'


def test_ts_new_param_as_new_options_argument():
    assert changed_lines(propose("C017"))[1].endswith('`/customers/${customerId}`, { query: { fields: "basic" } });')


def test_new_param_without_default_is_declined():
    proposal = propose("C018")
    assert proposal.empty
    assert "no default" in proposal.declined[0][1]


def test_python_removed_request_field():
    assert changed_lines(propose("C020")) == ['-            "note": note,']


def test_ts_removed_request_field():
    assert changed_lines(propose("C021"))[1] == "+    const body = { order_id: orderId, amount: amount };"


def test_python_removed_response_field_reads_with_get():
    assert changed_lines(propose("C022"))[1] == '+            note=data.get("note"),'


def test_unsupported_kinds_are_declined():
    for case_id in ("C024", "C026", "C028", "C031"):
        proposal = propose(case_id)
        assert proposal.empty, case_id
        assert "does not handle" in proposal.declined[0][1]


def test_partial_patch_on_mixed_case():
    proposal = propose("C035")
    assert proposal.handled and proposal.declined
    assert not proposal.empty


def test_never_touches_client_files_on_disk():
    before = (PY_CLIENT / "acme_client/client.py").read_text(), (TS_CLIENT / "src/client.ts").read_text()
    propose("C001")
    propose("C002")
    assert before == ((PY_CLIENT / "acme_client/client.py").read_text(), (TS_CLIENT / "src/client.ts").read_text())
