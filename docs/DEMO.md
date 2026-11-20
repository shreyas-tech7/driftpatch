# Demo

A real terminal session, written by `scripts/make_demo.sh` on 2026-11-20. Each block shows the exit code.

## List the breaking changes between v1 and v2

```console
$ driftpatch diff examples/acme/specs/acme-orders-v1.json examples/acme/specs/acme-orders-v2.json
3 breaking change(s) found by the built-in differ
  [renamed-field] The response field `total` in `Order` was renamed to `total_amount`.
  [removed-field] The response field `note` in `Order` was removed.
  [new-required-parameter] The query parameter `currency` of `GET /orders` is now required. Its default is `'USD'`.
(exit code 0)
```

## Find the call sites in the TypeScript client

```console
$ driftpatch find examples/acme/specs/acme-orders-v1.json examples/acme/specs/acme-orders-v2.json examples/acme/clients/ts
3 call site(s) for 3 change(s)
  src/client.ts:49:14 response-key 'total' in toOrder() <- renamed-field
  src/client.ts:53:13 response-key 'note' in toOrder() <- removed-field
  src/client.ts:83:23 endpoint-call 'currency' in listOrders() <- new-required-parameter
(exit code 0)
```

## Run the whole pipeline on the Python client

```console
$ driftpatch run examples/acme/specs/acme-orders-v1.json examples/acme/specs/acme-orders-v2.json examples/acme/clients/python --out out/demo
outcome: verified-patch
states: DIFF -> FIND -> PROPOSE -> VERIFY -> REPORT -> END
changes: 3  call sites: 3
verdict: pass  before: 6 failing  after: 0 failing  regressions: 0
wrote diff: out/demo/patch.diff
wrote pr: out/demo/PR.md
wrote report: out/demo/verification.md
wrote json: out/demo/verification.json
driftpatch did not push anything. Read the diff before you use it.
(exit code 0)
```

## The patch it wrote

```diff
--- a/acme_client/client.py
+++ b/acme_client/client.py
@@ -36,11 +36,11 @@
         return cls(
             id=data["id"],
             status=data["status"],
-            total=data["total"],
+            total=data["total_amount"],
             currency=data["currency"],
             customer_email=data["customer_email"],
             created_at=data["created_at"],
-            note=data["note"],
+            note=data.get("note"),
         )
 
 
@@ -93,7 +93,7 @@
             raise AcmeError(err.code, err.read().decode()) from None
 
     def list_orders(self, status="open", limit=10):
-        params = {"status": status, "limit": limit}
+        params = {"status": status, "limit": limit, "currency": "USD"}
         data = self._request("GET", "/orders", params=params)
         return [Order.from_api(o) for o in data["orders"]]
 
```

## A case the rule baseline declines

```console
$ driftpatch run examples/acme/specs/acme-orders-v1.json bench/cases/C031/new.json examples/acme/clients/python --out out/demo-declined
outcome: no-patch-proposed
states: DIFF -> FIND -> PROPOSE -> REPORT -> END
changes: 1  call sites: 1
wrote diff: out/demo-declined/patch.diff
wrote pr: out/demo-declined/PR.md
wrote report: out/demo-declined/verification.md
wrote json: out/demo-declined/verification.json
driftpatch did not push anything. Read the diff before you use it.
(exit code 1)
```

## Confirm the README tables

```console
$ driftpatch readme --check
README.md matches the results files.
(exit code 0)
```

