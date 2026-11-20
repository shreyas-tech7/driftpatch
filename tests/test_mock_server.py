"""The mock server built from a spec."""

import json
import urllib.error
import urllib.request

import pytest
from conftest import V1

from driftpatch.mock_server import MockServer, example_for, validate
from driftpatch.spec import load_spec


def call(server, method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(server.url + path, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as err:
        return err.code, json.loads(err.read())


@pytest.fixture
def server():
    with MockServer(load_spec(V1)) as s:
        yield s


def test_answers_with_examples(server):
    status, body = call(server, "GET", "/orders/ord_1001")
    assert status == 200
    assert body["total"] == 42.5 and body["id"] == "ord_1001"


def test_list_wraps_one_example(server):
    status, body = call(server, "GET", "/orders?status=open&limit=5")
    assert status == 200 and len(body["orders"]) == 1


def test_rejects_bad_enum_query(server):
    status, body = call(server, "GET", "/orders?status=lost")
    assert status == 400 and "not one of" in body["details"][0]


def test_rejects_non_integer_query(server):
    status, _ = call(server, "GET", "/orders?limit=ten")
    assert status == 400


def test_rejects_unknown_body_property(server):
    status, body = call(server, "POST", "/refunds", {"order_id": "o", "amount": 1.0, "colour": "red"})
    assert status == 400 and "unknown property 'colour'" in body["details"][0]


def test_rejects_missing_required_and_wrong_type(server):
    status, body = call(server, "POST", "/orders", {"items": [{"sku": "x", "quantity": "2"}]})
    assert status == 400
    joined = " ".join(body["details"])
    assert "customer_email" in joined and "expected integer" in joined


def test_created_status(server):
    status, body = call(server, "POST", "/refunds", {"order_id": "o", "amount": 1})
    assert status == 201 and body["id"] == "re_9"


def test_unknown_path_and_method(server):
    assert call(server, "GET", "/nope")[0] == 404
    assert call(server, "DELETE", "/orders")[0] == 405


def test_logs_requests(server):
    call(server, "GET", "/nope")
    assert server.requests[-1][2] == 404


def test_binds_loopback_only():
    with pytest.raises(ValueError):
        MockServer(load_spec(V1), host="0.0.0.0")


def test_example_and_validate_helpers():
    spec = {"components": {}}
    assert example_for(spec, {"type": "array", "items": {"type": "integer"}}) == [1]
    assert validate(spec, {"type": "boolean"}, 1) != []
    assert validate(spec, {"type": "string", "nullable": True}, None) == []
