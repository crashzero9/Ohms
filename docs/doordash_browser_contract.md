# DoorDash Browser-Automation Contract

This document defines the **schema-validated boundary** between Claude in Chrome
(running on the operator laptop) and OHMS (running on Replit).

DoorDash has no first-party API for merchant order capture, so we drive the
merchant portal with Claude in Chrome. Raw HTML from that browser session is
**never** allowed back into OHMS. Only schema-conforming JSON crosses the
boundary — this is a hard rule from Phase 3 security review finding **C3**
(return-path DoorDash tool must not accept blobs).

---

## Flow

```
┌─────────────────────────┐    1. routing instruction    ┌──────────────────┐
│  Violet / Claude (API)  │ ───────────────────────────▶ │       OHMS       │
│                         │     (tool call,               │                  │
│                         │      empty args)              │                  │
│                         │ ◀───────────────────────────  │                  │
│                         │    2. DoorDashRouting         └──────────────────┘
│                         │
│   Claude in Chrome      │ 3. opens DoorDash Merchant Portal
│   shortcut executes     │    • navigates to Orders tab
│                         │    • extracts structured JSON (no HTML)
│                         │
│                         │    4. schema-validated orders list
│                         │ ───────────────────────────▶ ┌──────────────────┐
│                         │     submit_doordash_orders   │       OHMS       │
│                         │     (orders=[...])           │  (schema-checked │
│                         │                              │   write scope)   │
│                         │ ◀───────────────────────────  │                  │
│                         │    5. DoorDashSubmission     └──────────────────┘
└─────────────────────────┘       {count, accepted}
```

---

## Step 1 — Routing call

Violet calls `get_doordash_orders_via_browser()`. No args.

The tool returns:

```json
{
  "method": "browser_automation",
  "instruction": "Open DoorDash Merchant Portal in Chrome. Extract pending orders as a schema-validated JSON list: [{order_id, customer_name, items: [{name, qty}], placed_at}]. Do not return raw HTML.",
  "tool": "Claude in Chrome",
  "status": "awaiting_browser_run",
  "correlation_id": "<32-hex>"
}
```

---

## Step 2 — Claude in Chrome extraction

Claude in Chrome executes a prepared shortcut that:

1. Navigates to the DoorDash Merchant Portal (operator is already signed in).
2. Reads the visible Orders list via `get_page_text` / structured DOM query.
3. Builds a JSON list matching this schema:

```json
[
  {
    "order_id": "DD-1234567890",
    "customer_name": "Jane Smith",
    "items": [
      { "name": "Monstera — 6in", "qty": 1 },
      { "name": "Watering can", "qty": 2 }
    ],
    "placed_at": "2026-04-19T14:22:00-04:00"
  }
]
```

**Hard rules enforced by the OHMS `submit_doordash_orders` tool:**

| Field | Rule |
|---|---|
| `order_id` | `str`, max 64 chars |
| `customer_name` | `str`, max 200 chars (also scrubbed from logs) |
| `items` | `list`, max 100 entries |
| `items[].name` | `str`, max 200 chars |
| `items[].qty` | `int`, 1 ≤ qty ≤ 500 |
| `placed_at` | `str`, max 64 chars (ISO-8601 expected) |
| `orders` (the outer list) | max 200 entries per call |

Any payload that violates these bounds is rejected with `ErrorEnvelope`
(`error: "invalid_input"`). No upstream DoorDash HTML, cookies, or headers
ever reach OHMS.

---

## Step 3 — Return-path submission

Claude in Chrome (or Violet on its behalf) calls:

```
submit_doordash_orders(orders=<validated list>)
```

OHMS re-validates the pydantic schema at the tool boundary. On success:

```json
{
  "correlation_id": "<32-hex>",
  "count": 1,
  "accepted": ["DD-1234567890"]
}
```

`count` is the number of orders that passed validation.
`accepted` is the list of `order_id` strings that passed.

---

## Mock payload (for Phase 3 integration tests)

```json
[
  {
    "order_id": "DD-TEST-0001",
    "customer_name": "Test Customer",
    "items": [
      { "name": "Succulent — 4in", "qty": 1 }
    ],
    "placed_at": "2026-04-19T15:00:00-04:00"
  }
]
```

---

## Why the round-trip

A single "pull DoorDash orders" tool would require OHMS to either (a) ship
and maintain a browser stack on Replit or (b) ingest arbitrary HTML from the
browser — both widen the blast radius. Splitting the flow means:

- **OHMS has no DoorDash credentials.** Only the operator's browser session
  does.
- **OHMS only accepts schema-validated JSON.** The browser cannot exfiltrate
  a raw page into OHMS.
- **Audit is clean.** Correlation IDs link the routing call to the submission.

This pattern can be copied for any future source that lacks an API (Instagram
DMs, SMS inbound, etc.).
