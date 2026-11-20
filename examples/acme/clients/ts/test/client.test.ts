// The client's own tests. They call a server at ACME_BASE_URL.
// driftpatch runs them against a mock server built from a spec.
import { test } from "node:test";
import assert from "node:assert/strict";
import { AcmeClient } from "../src/client.ts";

const client = () => new AcmeClient();

test("list orders", async () => {
  const orders = await client().listOrders();
  assert.equal(orders.length, 1);
  assert.equal(orders[0].id, "ord_1001");
});

test("order total", async () => {
  const order = await client().getOrder("ord_1001");
  assert.equal(order.total, 42.5);
});

test("order created at", async () => {
  const order = await client().getOrder("ord_1001");
  assert.equal(order.createdAt, "2026-11-01T10:00:00Z");
});

test("create order", async () => {
  const order = await client().createOrder("ada@example.org", [["SKU-RED-MUG", 2]], "gift");
  assert.equal(order.id, "ord_1001");
});

test("cancel order", async () => {
  const order = await client().cancelOrder("ord_1001");
  assert.equal(order.id, "ord_1001");
});

test("cancel for fraud", async () => {
  const order = await client().cancelForFraud("ord_1001");
  assert.equal(order.id, "ord_1001");
});

test("list items", async () => {
  const items = await client().listItems("ord_1001");
  assert.equal(items[0].unitPrice, 21.25);
});

test("get customer", async () => {
  const customer = await client().getCustomer("cus_501");
  assert.equal(customer.name, "Ada Lovelace");
});

test("create refund", async () => {
  const refund = await client().createRefund("ord_1001", 10.0);
  assert.equal(refund.id, "re_9");
});
