"""The client's own tests. They call a server at ACME_BASE_URL.

driftpatch runs these tests against a mock server built from a spec.
The values come from the `example` fields in the spec.
"""

from acme_client import AcmeClient


def client():
    return AcmeClient()


def test_list_orders():
    orders = client().list_orders()
    assert len(orders) == 1
    assert orders[0].id == "ord_1001"


def test_order_total():
    order = client().get_order("ord_1001")
    assert order.total == 42.5
    assert order.currency == "USD"


def test_order_customer_email():
    order = client().get_order("ord_1001")
    assert order.customer_email == "ada@example.org"


def test_list_cancelled_orders():
    assert len(client().list_cancelled_orders()) == 1


def test_create_order():
    order = client().create_order("ada@example.org", [("SKU-RED-MUG", 2)], note="gift")
    assert order.id == "ord_1001"


def test_cancel_order():
    order = client().cancel_order("ord_1001")
    assert order.id == "ord_1001"


def test_list_items():
    items = client().list_items("ord_1001")
    assert items[0].sku == "SKU-RED-MUG"
    assert items[0].unit_price == 21.25


def test_get_shipment():
    shipment = client().get_shipment("ord_1001")
    assert shipment.tracking_number == "1Z999AA10123456784"


def test_get_customer():
    customer = client().get_customer("cus_501")
    assert customer.name == "Ada Lovelace"


def test_create_refund():
    refund = client().create_refund("ord_1001", 10.0)
    assert refund.id == "re_9"
    assert refund.status == "pending"
