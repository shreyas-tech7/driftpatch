"""Acme Orders API client, written against spec v1.

This file is the code that driftpatch reads and patches. It uses only the
standard library so its tests run anywhere.
"""

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass


class AcmeError(Exception):
    """The API answered with an error status."""

    def __init__(self, status, body):
        super().__init__(f"Acme API error {status}: {body}")
        self.status = status
        self.body = body


@dataclass
class Order:
    id: str
    status: str
    total: float
    currency: str
    customer_email: str
    created_at: str
    note: str

    @classmethod
    def from_api(cls, data):
        return cls(
            id=data["id"],
            status=data["status"],
            total=data["total"],
            currency=data["currency"],
            customer_email=data["customer_email"],
            created_at=data["created_at"],
            note=data["note"],
        )


@dataclass
class LineItem:
    sku: str
    quantity: int
    unit_price: float


@dataclass
class Shipment:
    id: str
    carrier: str
    tracking_number: str
    status: str


@dataclass
class Customer:
    id: str
    email: str
    name: str
    tier: str


@dataclass
class Refund:
    id: str
    order_id: str
    amount: float
    status: str


class AcmeClient:
    def __init__(self, base_url=None, timeout=5):
        self.base_url = (base_url or os.environ.get("ACME_BASE_URL", "http://127.0.0.1:8080")).rstrip("/")
        self.timeout = timeout

    def _request(self, method, path, params=None, body=None):
        url = self.base_url + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read() or b"null")
        except urllib.error.HTTPError as err:
            raise AcmeError(err.code, err.read().decode()) from None

    def list_orders(self, status="open", limit=10):
        params = {"status": status, "limit": limit}
        data = self._request("GET", "/orders", params=params)
        return [Order.from_api(o) for o in data["orders"]]

    def list_cancelled_orders(self):
        return self.list_orders(status="cancelled")

    def get_order(self, order_id):
        return Order.from_api(self._request("GET", f"/orders/{order_id}"))

    def create_order(self, customer_email, items, note=""):
        body = {
            "customer_email": customer_email,
            "items": [{"sku": sku, "quantity": quantity} for sku, quantity in items],
            "note": note,
        }
        return Order.from_api(self._request("POST", "/orders", body=body))

    def cancel_order(self, order_id, reason="customer_request"):
        body = {"reason": reason}
        return Order.from_api(self._request("POST", f"/orders/{order_id}/cancel", body=body))

    def list_items(self, order_id):
        data = self._request("GET", f"/orders/{order_id}/items")
        return [LineItem(sku=i["sku"], quantity=i["quantity"], unit_price=i["unit_price"]) for i in data["items"]]

    def get_shipment(self, order_id):
        data = self._request("GET", f"/orders/{order_id}/shipment")
        return Shipment(
            id=data["id"],
            carrier=data["carrier"],
            tracking_number=data["tracking_number"],
            status=data["status"],
        )

    def get_customer(self, customer_id):
        data = self._request("GET", f"/customers/{customer_id}")
        return Customer(id=data["id"], email=data["email"], name=data["name"], tier=data["tier"])

    def create_refund(self, order_id, amount, reason="damaged"):
        body = {"order_id": order_id, "amount": amount, "reason": reason}
        data = self._request("POST", "/refunds", body=body)
        return Refund(id=data["id"], order_id=data["order_id"], amount=data["amount"], status=data["status"])
