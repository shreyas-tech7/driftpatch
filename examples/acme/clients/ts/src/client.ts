// Acme Orders API client, written against spec v1.
// This file is the code that driftpatch reads and patches.
// It runs on Node 22 with type stripping and has no npm dependencies.

export interface Order {
  id: string;
  status: string;
  total: number;
  currency: string;
  customerEmail: string;
  createdAt: string;
  note: string;
}

export interface LineItem {
  sku: string;
  quantity: number;
  unitPrice: number;
}

export interface Customer {
  id: string;
  email: string;
  name: string;
  tier: string;
}

export interface Refund {
  id: string;
  orderId: string;
  amount: number;
  status: string;
}

export class AcmeError extends Error {
  status: number;
  constructor(status: number, body: string) {
    super(`Acme API error ${status}: ${body}`);
    this.status = status;
  }
}

type RequestOptions = { query?: Record<string, string>; body?: unknown };

export function toOrder(raw: any): Order {
  return {
    id: raw.id,
    status: raw.status,
    total: raw.total,
    currency: raw.currency,
    customerEmail: raw.customer_email,
    createdAt: raw.created_at,
    note: raw.note,
  };
}

export class AcmeClient {
  baseUrl: string;

  constructor(baseUrl?: string) {
    this.baseUrl = (baseUrl ?? process.env.ACME_BASE_URL ?? "http://127.0.0.1:8080").replace(/\/$/, "");
  }

  async request(method: string, path: string, opts: RequestOptions = {}): Promise<any> {
    let url = this.baseUrl + path;
    if (opts.query) {
      url += "?" + new URLSearchParams(opts.query).toString();
    }
    const init: RequestInit = { method, headers: { "Content-Type": "application/json" } };
    if (opts.body !== undefined) {
      init.body = JSON.stringify(opts.body);
    }
    const resp = await fetch(url, { ...init, signal: AbortSignal.timeout(5000) });
    const text = await resp.text();
    if (!resp.ok) {
      throw new AcmeError(resp.status, text);
    }
    return text ? JSON.parse(text) : null;
  }

  async listOrders(status = "open", limit = 10): Promise<Order[]> {
    const query = { status: status, limit: String(limit) };
    const data = await this.request("GET", "/orders", { query });
    return data.orders.map(toOrder);
  }

  async getOrder(orderId: string): Promise<Order> {
    return toOrder(await this.request("GET", `/orders/${orderId}`));
  }

  async createOrder(customerEmail: string, items: [string, number][], note = ""): Promise<Order> {
    const body = {
      customer_email: customerEmail,
      items: items.map(([sku, quantity]) => ({ sku: sku, quantity: quantity })),
      note: note,
    };
    return toOrder(await this.request("POST", "/orders", { body }));
  }

  async cancelOrder(orderId: string, reason = "customer_request"): Promise<Order> {
    const body = { reason: reason };
    return toOrder(await this.request("POST", `/orders/${orderId}/cancel`, { body }));
  }

  async cancelForFraud(orderId: string): Promise<Order> {
    return this.cancelOrder(orderId, "fraud");
  }

  async listItems(orderId: string): Promise<LineItem[]> {
    const data = await this.request("GET", `/orders/${orderId}/items`);
    return data.items.map((i: any) => ({ sku: i.sku, quantity: i.quantity, unitPrice: i.unit_price }));
  }

  async getCustomer(customerId: string): Promise<Customer> {
    const data = await this.request("GET", `/customers/${customerId}`);
    return { id: data.id, email: data.email, name: data.name, tier: data.tier };
  }

  async createRefund(orderId: string, amount: number, reason = "damaged"): Promise<Refund> {
    const body = { order_id: orderId, amount: amount, reason: reason };
    const data = await this.request("POST", "/refunds", { body });
    return { id: data.id, orderId: data.order_id, amount: data.amount, status: data.status };
  }
}
