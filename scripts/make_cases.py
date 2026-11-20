"""Write the frozen benchmark suite in bench/cases.

Each case starts from Acme Orders spec v1 and applies one or two breaking
changes. Each case also carries one known correct patch for the sample client,
written by the case author as exact text edits. The oracle proposer replays
that patch, so a case is only valid if the oracle passes the verifier on it.

Run:  python scripts/make_cases.py          # write the cases and the manifest
      python scripts/make_cases.py --check  # fail if the files on disk differ
"""

import argparse
import copy
import hashlib
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from driftpatch.patch import make_diff  # noqa: E402

V1 = "examples/acme/specs/acme-orders-v1.json"
CLIENTS = {"python": "examples/acme/clients/python", "ts": "examples/acme/clients/ts"}
CLIENT_FILE = {"python": "acme_client/client.py", "ts": "src/client.ts"}
SPLIT_SEED = 20261120
DEV_COUNT = 25


# ---------------------------------------------------------------- spec edits


def schema(spec, name):
    return spec["components"]["schemas"][name]


def rename_prop(spec, name, old, new):
    s = schema(spec, name)
    s["properties"] = {(new if k == old else k): v for k, v in s["properties"].items()}
    s["required"] = [new if r == old else r for r in s.get("required", [])]


def remove_prop(spec, name, prop):
    s = schema(spec, name)
    del s["properties"][prop]
    s["required"] = [r for r in s.get("required", []) if r != prop]


def set_type(spec, name, prop, type_, example):
    s = schema(spec, name)["properties"][prop]
    s["type"] = type_
    s["example"] = example


def set_prop_enum(spec, name, prop, values, example=None):
    s = schema(spec, name)["properties"][prop]
    s["enum"] = values
    if example is not None:
        s["example"] = example


def set_param_enum(spec, path, method, param, values, default=None):
    for p in spec["paths"][path][method]["parameters"]:
        if p["name"] == param:
            p["schema"]["enum"] = values
            if default is not None:
                p["schema"]["default"] = default


def add_query(spec, path, method, name, default=None, example=None):
    sch = {"type": "string"}
    if default is not None:
        sch["default"] = default
    if example is not None:
        sch["example"] = example
    op = spec["paths"][path][method]
    op.setdefault("parameters", []).append({"name": name, "in": "query", "required": True, "schema": sch})


def move_path(spec, old, new):
    spec["paths"] = {(new if k == old else k): v for k, v in spec["paths"].items()}


# ---------------------------------------------------------------- the cases
# Each case: (language, title, [spec edit functions], [(old text, new text)] client edits)

CASES = [
    (
        "python",
        "Order.total renamed to total_amount",
        [lambda s: rename_prop(s, "Order", "total", "total_amount")],
        [('total=data["total"]', 'total=data["total_amount"]')],
    ),
    (
        "ts",
        "Order.total renamed to total_amount",
        [lambda s: rename_prop(s, "Order", "total", "total_amount")],
        [("total: raw.total,", "total: raw.total_amount,")],
    ),
    (
        "python",
        "Order.customer_email renamed to email in responses",
        [lambda s: rename_prop(s, "Order", "customer_email", "email")],
        [('customer_email=data["customer_email"]', 'customer_email=data["email"]')],
    ),
    (
        "ts",
        "Customer.name renamed to full_name",
        [lambda s: rename_prop(s, "Customer", "name", "full_name")],
        [("name: data.name,", "name: data.full_name,")],
    ),
    (
        "python",
        "Shipment.tracking_number renamed to tracking_code",
        [lambda s: rename_prop(s, "Shipment", "tracking_number", "tracking_code")],
        [('tracking_number=data["tracking_number"]', 'tracking_number=data["tracking_code"]')],
    ),
    (
        "ts",
        "LineItem.unit_price renamed to price",
        [lambda s: rename_prop(s, "LineItem", "unit_price", "price")],
        [("unitPrice: i.unit_price", "unitPrice: i.price")],
    ),
    (
        "python",
        "Refund.status renamed to state (Order also has a status field)",
        [lambda s: rename_prop(s, "Refund", "status", "state")],
        [('amount=data["amount"], status=data["status"])', 'amount=data["amount"], status=data["state"])')],
    ),
    (
        "ts",
        "Order.created_at renamed to created",
        [lambda s: rename_prop(s, "Order", "created_at", "created")],
        [("createdAt: raw.created_at,", "createdAt: raw.created,")],
    ),
    (
        "python",
        "CreateOrder.customer_email renamed to email in requests",
        [lambda s: rename_prop(s, "CreateOrder", "customer_email", "email")],
        [('"customer_email": customer_email,', '"email": customer_email,')],
    ),
    (
        "ts",
        "CreateOrder.note renamed to comment",
        [lambda s: rename_prop(s, "CreateOrder", "note", "comment")],
        [("      note: note,", "      comment: note,")],
    ),
    (
        "python",
        "CreateRefund.amount renamed to refund_amount",
        [lambda s: rename_prop(s, "CreateRefund", "amount", "refund_amount")],
        [('"amount": amount, "reason": reason}', '"refund_amount": amount, "reason": reason}')],
    ),
    (
        "ts",
        "CancelRequest.reason renamed to cancel_reason",
        [lambda s: rename_prop(s, "CancelRequest", "reason", "cancel_reason")],
        [("const body = { reason: reason };", "const body = { cancel_reason: reason };")],
    ),
    (
        "python",
        "LineItemInput.quantity renamed to qty",
        [lambda s: rename_prop(s, "LineItemInput", "quantity", "qty")],
        [('{"sku": sku, "quantity": quantity}', '{"sku": sku, "qty": quantity}')],
    ),
    (
        "python",
        "GET /orders needs a currency query parameter (default USD)",
        [lambda s: add_query(s, "/orders", "get", "currency", default="USD")],
        [('params = {"status": status, "limit": limit}', 'params = {"status": status, "limit": limit, "currency": "USD"}')],
    ),
    (
        "ts",
        "GET /orders needs a currency query parameter (default USD)",
        [lambda s: add_query(s, "/orders", "get", "currency", default="USD")],
        [
            (
                "const query = { status: status, limit: String(limit) };",
                'const query = { status: status, limit: String(limit), currency: "USD" };',
            )
        ],
    ),
    (
        "python",
        "GET /orders/{order_id}/items needs an expand query parameter (default none)",
        [lambda s: add_query(s, "/orders/{order_id}/items", "get", "expand", default="none")],
        [
            (
                'self._request("GET", f"/orders/{order_id}/items")',
                'self._request("GET", f"/orders/{order_id}/items", params={"expand": "none"})',
            )
        ],
    ),
    (
        "ts",
        "GET /customers/{customer_id} needs a fields query parameter (default basic)",
        [lambda s: add_query(s, "/customers/{customer_id}", "get", "fields", default="basic")],
        [
            (
                'this.request("GET", `/customers/${customerId}`)',
                'this.request("GET", `/customers/${customerId}`, { query: { fields: "basic" } })',
            )
        ],
    ),
    (
        "python",
        "GET /orders/{order_id}/shipment needs a region query parameter (no default)",
        [lambda s: add_query(s, "/orders/{order_id}/shipment", "get", "region", example="us")],
        [
            (
                'self._request("GET", f"/orders/{order_id}/shipment")',
                'self._request("GET", f"/orders/{order_id}/shipment", params={"region": "us"})',
            )
        ],
    ),
    (
        "ts",
        "GET /orders needs an api_version query parameter (no default)",
        [lambda s: add_query(s, "/orders", "get", "api_version", example="2026-11-01")],
        [
            (
                "const query = { status: status, limit: String(limit) };",
                'const query = { status: status, limit: String(limit), api_version: "2026-11-01" };',
            )
        ],
    ),
    (
        "python",
        "CreateOrder.note removed from requests",
        [lambda s: remove_prop(s, "CreateOrder", "note")],
        [('            "note": note,\n', "")],
    ),
    (
        "ts",
        "CreateRefund.reason removed from requests",
        [lambda s: remove_prop(s, "CreateRefund", "reason")],
        [("const body = { order_id: orderId, amount: amount, reason: reason };", "const body = { order_id: orderId, amount: amount };")],
    ),
    (
        "python",
        "Order.note removed from responses",
        [lambda s: remove_prop(s, "Order", "note")],
        [('note=data["note"],', 'note=data.get("note"),')],
    ),
    (
        "python",
        "Shipment.carrier removed from responses",
        [lambda s: remove_prop(s, "Shipment", "carrier")],
        [('carrier=data["carrier"],', 'carrier=data.get("carrier"),')],
    ),
    (
        "python",
        "LineItemInput.quantity changed from integer to string",
        [lambda s: set_type(s, "LineItemInput", "quantity", "string", "2")],
        [('{"sku": sku, "quantity": quantity}', '{"sku": sku, "quantity": str(quantity)}')],
    ),
    (
        "ts",
        "LineItemInput.quantity changed from integer to string",
        [lambda s: set_type(s, "LineItemInput", "quantity", "string", "2")],
        [("({ sku: sku, quantity: quantity })", "({ sku: sku, quantity: String(quantity) })")],
    ),
    (
        "python",
        "Order.total changed from number to string",
        [lambda s: set_type(s, "Order", "total", "string", "42.50")],
        [('total=data["total"],', 'total=float(data["total"]),')],
    ),
    (
        "ts",
        "CreateRefund.amount changed from number to string",
        [lambda s: set_type(s, "CreateRefund", "amount", "string", "10.00")],
        [("amount: amount, reason: reason };", "amount: String(amount), reason: reason };")],
    ),
    (
        "python",
        "Order status value open renamed to active",
        [
            lambda s: set_param_enum(s, "/orders", "get", "status", ["active", "shipped", "cancelled"], default="active"),
            lambda s: set_prop_enum(s, "Order", "status", ["active", "shipped", "cancelled"], example="active"),
        ],
        [('def list_orders(self, status="open", limit=10):', 'def list_orders(self, status="active", limit=10):')],
    ),
    (
        "ts",
        "Cancel reason fraud renamed to suspected_fraud",
        [lambda s: set_prop_enum(s, "CancelRequest", "reason", ["customer_request", "suspected_fraud", "out_of_stock"])],
        [('this.cancelOrder(orderId, "fraud")', 'this.cancelOrder(orderId, "suspected_fraud")')],
    ),
    (
        "python",
        "Order status value cancelled respelled as canceled",
        [
            lambda s: set_param_enum(s, "/orders", "get", "status", ["open", "shipped", "canceled"]),
            lambda s: set_prop_enum(s, "Order", "status", ["open", "shipped", "canceled"]),
        ],
        [('return self.list_orders(status="cancelled")', 'return self.list_orders(status="canceled")')],
    ),
    (
        "python",
        "POST /orders/{order_id}/cancel moved to /orders/{order_id}/cancellation",
        [lambda s: move_path(s, "/orders/{order_id}/cancel", "/orders/{order_id}/cancellation")],
        [('f"/orders/{order_id}/cancel"', 'f"/orders/{order_id}/cancellation"')],
    ),
    (
        "ts",
        "GET /orders/{order_id}/items moved to /orders/{order_id}/line-items",
        [lambda s: move_path(s, "/orders/{order_id}/items", "/orders/{order_id}/line-items")],
        [("`/orders/${orderId}/items`", "`/orders/${orderId}/line-items`")],
    ),
    (
        "python",
        "GET /customers/{customer_id} moved to /accounts/{customer_id}",
        [lambda s: move_path(s, "/customers/{customer_id}", "/accounts/{customer_id}")],
        [('f"/customers/{customer_id}"', 'f"/accounts/{customer_id}"')],
    ),
    (
        "python",
        "Two changes: Order.total renamed and a required currency parameter",
        [lambda s: rename_prop(s, "Order", "total", "total_amount"), lambda s: add_query(s, "/orders", "get", "currency", default="USD")],
        [
            ('total=data["total"]', 'total=data["total_amount"]'),
            ('params = {"status": status, "limit": limit}', 'params = {"status": status, "limit": limit, "currency": "USD"}'),
        ],
    ),
    (
        "ts",
        "Two changes: CreateOrder.note renamed and quantity changed to string",
        [lambda s: rename_prop(s, "CreateOrder", "note", "comment"), lambda s: set_type(s, "LineItemInput", "quantity", "string", "2")],
        [
            ("      note: note,", "      comment: note,"),
            ("({ sku: sku, quantity: quantity })", "({ sku: sku, quantity: String(quantity) })"),
        ],
    ),
    (
        "python",
        "Two changes: cancel endpoint moved and Order.note removed",
        [lambda s: move_path(s, "/orders/{order_id}/cancel", "/orders/{order_id}/cancellation"), lambda s: remove_prop(s, "Order", "note")],
        [('f"/orders/{order_id}/cancel"', 'f"/orders/{order_id}/cancellation"'), ('note=data["note"],', 'note=data.get("note"),')],
    ),
]


V2 = "examples/acme/specs/acme-orders-v2.json"
V2_EDITS = [
    lambda s: rename_prop(s, "Order", "total", "total_amount"),
    lambda s: add_query(s, "/orders", "get", "currency", default="USD"),
    lambda s: remove_prop(s, "Order", "note"),
]


def build_v2(v1):
    """Spec v2 for the demo: three changes that the rule baseline can fix."""
    spec = copy.deepcopy(v1)
    spec["info"]["version"] = "2.0.0"
    for edit in V2_EDITS:
        edit(spec)
    return json.dumps(spec, indent=2) + "\n"


def splits(n):
    ids = list(range(n))
    random.Random(SPLIT_SEED).shuffle(ids)
    dev = set(ids[:DEV_COUNT])
    return ["dev" if i in dev else "heldout" for i in range(n)]


def build():
    """Return {relative path: text} for every file of the suite."""
    v1 = json.loads((ROOT / V1).read_text())
    files = {V2: build_v2(v1)}
    for i, ((lang, title, spec_edits, client_edits), split) in enumerate(zip(CASES, splits(len(CASES)), strict=True), start=1):
        cid = f"C{i:03d}"
        spec = copy.deepcopy(v1)
        spec["info"]["version"] = f"2.0.0-{cid.lower()}"
        for edit in spec_edits:
            edit(spec)
        rel = CLIENT_FILE[lang]
        original = (ROOT / CLIENTS[lang] / rel).read_text()
        patched = original
        for old, new in client_edits:
            if patched.count(old) != 1:
                raise SystemExit(f"{cid}: edit text must occur once in {rel}: {old!r} (found {patched.count(old)})")
            patched = patched.replace(old, new)
        case = {
            "id": cid,
            "title": title,
            "language": lang,
            "client": CLIENTS[lang],
            "old_spec": V1,
            "new_spec": f"bench/cases/{cid}/new.json",
            "expected_patch": f"bench/cases/{cid}/expected.diff",
            "split": split,
            "license": "MIT",
        }
        base = f"bench/cases/{cid}"
        files[f"{base}/case.json"] = json.dumps(case, indent=2) + "\n"
        files[f"{base}/new.json"] = json.dumps(spec, indent=2) + "\n"
        files[f"{base}/expected.diff"] = make_diff({rel: original}, {rel: patched})
    return files


def manifest(files):
    """SHA-256 of every case file plus the spec and clients the cases depend on."""
    entries = dict(files)
    for rel in [V1, *[f"{c}/{f}" for c in CLIENTS.values() for f in _client_files(c)]]:
        entries[rel] = (ROOT / rel).read_text()
    lines = [f"{hashlib.sha256(text.encode()).hexdigest()}  {rel}" for rel, text in sorted(entries.items())]
    return "\n".join(lines) + "\n"


def _client_files(client):
    out = []
    for p in sorted((ROOT / client).rglob("*")):
        if p.is_file() and not any(part in ("__pycache__", ".pytest_cache", "node_modules") for part in p.parts):
            out.append(p.relative_to(ROOT / client).as_posix())
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="fail if the files on disk differ from a fresh build")
    args = ap.parse_args(argv)
    files = build()
    files["bench/MANIFEST.sha256"] = manifest(files)
    bad = []
    for rel, text in files.items():
        path = ROOT / rel
        if args.check:
            if not path.exists() or path.read_text() != text:
                bad.append(rel)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
    if args.check:
        on_disk = {p.relative_to(ROOT).as_posix() for p in (ROOT / "bench/cases").rglob("*") if p.is_file()}
        extra = sorted(on_disk - set(files))

        if bad or extra:
            print("out of date:", *bad, *[f"extra: {e}" for e in extra], sep="\n  ")
            return 1
        print(f"{len(CASES)} cases match a fresh build")
        return 0
    print(f"wrote {len(CASES)} cases to bench/cases")
    return 0


if __name__ == "__main__":
    sys.exit(main())
