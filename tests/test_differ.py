"""The built-in differ: one test per kind, plus the rename heuristic."""

import copy

from driftpatch import differ
from driftpatch.differ import diff_specs


def _schema(spec, name):
    return spec["components"]["schemas"][name]


def kinds(changes):
    return sorted(c.kind for c in changes)


def test_same_spec_has_no_changes(v1):
    assert diff_specs(v1, copy.deepcopy(v1)) == []


def test_removed_endpoint(v1):
    new = copy.deepcopy(v1)
    del new["paths"]["/refunds"]
    changes = diff_specs(v1, new)
    assert kinds(changes) == [differ.REMOVED_ENDPOINT]
    assert changes[0].path == "/refunds" and changes[0].method == "post"


def test_path_parameter_rename_is_not_a_removed_endpoint(v1):
    new = copy.deepcopy(v1)
    new["paths"]["/orders/{id}"] = new["paths"].pop("/orders/{order_id}")
    assert differ.REMOVED_ENDPOINT not in kinds(diff_specs(v1, new))


def test_renamed_response_field_is_credited_to_every_operation(v1):
    new = copy.deepcopy(v1)
    order = _schema(new, "Order")
    order["properties"]["total_amount"] = order["properties"].pop("total")
    changes = diff_specs(v1, new)
    assert kinds(changes) == [differ.RENAMED_FIELD]
    c = changes[0]
    assert (c.schema, c.field, c.new_field, c.location) == ("Order", "total", "total_amount", "response")
    # Order comes back from five operations, one of them through OrderList.
    assert sorted(c.operations) == sorted(["GET /orders", "POST /orders", "GET /orders/{order_id}", "POST /orders/{order_id}/cancel"])


def test_removed_field_without_partner(v1):
    new = copy.deepcopy(v1)
    del _schema(new, "Shipment")["properties"]["carrier"]
    changes = diff_specs(v1, new)
    assert kinds(changes) == [differ.REMOVED_FIELD]
    assert changes[0].field == "carrier"


def test_removed_and_added_of_other_type_is_not_a_rename(v1):
    new = copy.deepcopy(v1)
    props = _schema(new, "Shipment")["properties"]
    del props["carrier"]
    props["weight_grams"] = {"type": "integer"}
    assert kinds(diff_specs(v1, new)) == [differ.REMOVED_FIELD]


def test_x_renamed_from_wins(v1):
    new = copy.deepcopy(v1)
    props = _schema(new, "Customer")["properties"]
    del props["name"]
    props["zzz"] = {"type": "string", "x-renamed-from": "name"}
    props["named"] = {"type": "string"}
    changes = [c for c in diff_specs(v1, new) if c.kind == differ.RENAMED_FIELD]
    assert [(c.field, c.new_field) for c in changes] == [("name", "zzz")]


def test_new_required_query_parameter_keeps_its_default(v1):
    new = copy.deepcopy(v1)
    new["paths"]["/orders"]["get"]["parameters"].append(
        {"name": "currency", "in": "query", "required": True, "schema": {"type": "string", "default": "USD"}}
    )
    (c,) = diff_specs(v1, new)
    assert (c.kind, c.location, c.field, c.has_default, c.default) == (differ.NEW_REQUIRED_PARAMETER, "query", "currency", True, "USD")


def test_optional_parameter_that_becomes_required(v1):
    new = copy.deepcopy(v1)
    new["paths"]["/orders"]["get"]["parameters"][1]["required"] = True
    (c,) = diff_specs(v1, new)
    assert c.kind == differ.NEW_REQUIRED_PARAMETER and c.field == "limit"


def test_new_required_body_property(v1):
    new = copy.deepcopy(v1)
    _schema(new, "CreateRefund")["required"].append("reason")
    (c,) = diff_specs(v1, new)
    assert (c.kind, c.location, c.field) == (differ.NEW_REQUIRED_PARAMETER, "request", "reason")


def test_changed_type(v1):
    new = copy.deepcopy(v1)
    _schema(new, "LineItemInput")["properties"]["quantity"]["type"] = "string"
    (c,) = diff_specs(v1, new)
    assert (c.kind, c.location, c.field, c.old_type, c.new_type) == (differ.CHANGED_TYPE, "request", "quantity", "integer", "string")


def test_changed_parameter_type(v1):
    new = copy.deepcopy(v1)
    new["paths"]["/orders"]["get"]["parameters"][1]["schema"]["type"] = "string"
    (c,) = diff_specs(v1, new)
    assert (c.kind, c.location, c.field) == (differ.CHANGED_TYPE, "query", "limit")


def test_changed_enum_lost_value(v1):
    new = copy.deepcopy(v1)
    _schema(new, "CancelRequest")["properties"]["reason"]["enum"] = ["customer_request", "suspected_fraud", "out_of_stock"]
    (c,) = diff_specs(v1, new)
    assert c.kind == differ.CHANGED_ENUM and c.removed_values == ["fraud"]


def test_added_request_enum_value_is_not_breaking(v1):
    new = copy.deepcopy(v1)
    _schema(new, "CancelRequest")["properties"]["reason"]["enum"].append("other")
    assert diff_specs(v1, new) == []


def test_added_response_enum_value_is_breaking(v1):
    new = copy.deepcopy(v1)
    _schema(new, "Shipment")["properties"]["status"]["enum"].append("returned")
    (c,) = diff_specs(v1, new)
    assert c.kind == differ.CHANGED_ENUM and c.added_values == ["returned"]


def test_cycles_do_not_loop(v1):
    old = copy.deepcopy(v1)
    for spec in (old, copy.deepcopy(v1)):
        _schema(spec, "Customer")["properties"]["referrer"] = {"$ref": "#/components/schemas/Customer"}
    new = copy.deepcopy(old)
    del _schema(new, "Customer")["properties"]["tier"]
    assert kinds(diff_specs(old, new)) == [differ.REMOVED_FIELD]


def test_describe_and_count(v1):
    new = copy.deepcopy(v1)
    del new["paths"]["/refunds"]
    changes = diff_specs(v1, new)
    assert "removed" in changes[0].describe()
    assert differ.count_by_kind(changes)[differ.REMOVED_ENDPOINT] == 1


def test_form_request_body_is_compared():
    """Stripe sends form bodies. A new required form field counts like a JSON one."""

    def spec(required):
        body = {"type": "object", "properties": {"amount": {"type": "integer"}, "currency": {"type": "string"}}, "required": required}
        return {
            "openapi": "3.0.0",
            "paths": {
                "/charges": {
                    "post": {
                        "requestBody": {"content": {"application/x-www-form-urlencoded": {"schema": body}}},
                        "responses": {"200": {"description": "ok"}},
                    }
                }
            },
        }

    changes = diff_specs(spec(["amount"]), spec(["amount", "currency"]))
    assert [(c.kind, c.field) for c in changes] == [("new-required-parameter", "currency")]
