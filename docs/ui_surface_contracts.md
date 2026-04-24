# OHMS UI Surface Contracts

OHMS is a data-and-control plane. The three UI surfaces (Order Board, User
Tablet, Voice Prompt) each consume OHMS through a **scoped token** and a
**restricted tool set**. No surface sees the raw Shopify payload; all traffic
rides the same hardened middleware stack and the same pydantic return models.

This document is the source of truth for each surface's permissions. If a
surface needs something not listed here, the correct path is to propose an
additional tool or scope — never widen an existing one.

---

## 1 — Order Board (fulfillment view)

**Audience:** fulfillment staff on a shared in-shop screen.
**Medium:** web, read-mostly.
**Scope token:** `OHMS_API_TOKEN_READ`.

### Tools allowed
| Tool | Purpose |
|---|---|
| `list_pending_orders(limit)` | drive the board's main grid |
| `get_order(order_id)` | expand a single card |
| `get_inventory_snapshot(limit)` | show low-stock banner |

### Tools NOT allowed
- `update_order_status` — status changes happen on the User Tablet only.
- `submit_doordash_orders` — never from a shared screen.
- `print_order_ticket` — triggered by the tablet workflow.

### Refresh cadence
Poll `list_pending_orders` every 30s. If rate limits trigger (`429`), the
board shows a muted banner and backs off to 60s.

### Failure posture
On any `ErrorEnvelope`, show a neutral "couldn't refresh" message with the
`correlation_id` in small text. Never surface raw error strings to the
shop floor.

---

## 2 — User Tablet (fulfiller controls)

**Audience:** the fulfiller working an order.
**Medium:** single-user tablet (passcode-locked).
**Scope token:** `OHMS_API_TOKEN_WRITE`.

### Tools allowed
| Tool | Purpose |
|---|---|
| `get_order(order_id)` | inspect before acting |
| `update_order_status(order_id, status, idempotency_key)` | advance workflow |
| `print_order_ticket(order_id)` | fire the receipt printer |
| `submit_doordash_orders(orders)` | manual walk-in override |
| `get_inventory_snapshot(limit)` | check stock during pick |

### Idempotency requirement (Phase 3 H-item)
Every `update_order_status` call **must** include a client-generated UUIDv4
as `idempotency_key`. Tapping the same button twice within 24h returns the
cached result with `idempotent_replay: true` instead of double-writing. The
tablet is responsible for generating and retaining the key per user action.

### UX rule
Show the order number in plain sight before any write. A confirmation sheet
is required for any status transition that cannot be undone
(`out_for_delivery`, `delivered`, `cancelled`, `refunded`).

---

## 3 — Voice Prompt (hands-free assist)

**Audience:** fulfiller, hands full.
**Medium:** voice, same device as User Tablet.
**Scope token:** `OHMS_API_TOKEN_WRITE` (inherited from tablet session).

### Tools allowed — read
| Tool | Purpose |
|---|---|
| `get_order(order_id)` | "What's in order 4421?" |
| `list_pending_orders(limit)` | "How many orders are waiting?" |
| `get_inventory_snapshot(limit)` | "Are we out of monsteras?" |

### Tools allowed — write (with explicit confirmation)
| Tool | Purpose |
|---|---|
| `update_order_status(order_id, status, idempotency_key)` | only after `"Yes, mark it <status>"` |
| `print_order_ticket(order_id)` | only after `"Yes, print the ticket"` |

### Voice confirmation rule (mandatory)
Every write from voice **must** complete a two-turn confirmation:

1. Voice assistant restates the intent: *"Mark order 4421 out for delivery — confirm?"*
2. Fulfiller says a positive affirmation (`yes`, `confirm`, `do it`).

Negative or ambiguous responses abort the action. No write fires on a single
utterance. The idempotency_key is generated at turn 1 and reused at turn 2 so
a re-prompt doesn't double-fire.

### Tools NOT allowed
- `submit_doordash_orders` — never from voice. Walk-ins stay on the tablet
  where the fulfiller can see the items list.

---

## Token and logging posture

- Tokens are distinct per surface in Phase 3+:
  - `OHMS_API_TOKEN_READ` — Order Board only.
  - `OHMS_API_TOKEN_WRITE` — User Tablet + Voice Prompt.
- Each request carries an `X-OHMS-Request-ID` (server-generated if absent).
- `CorrelationIdMiddleware` tags every log line with that ID.
- The logging filter scrubs `Authorization`, `X-Shopify-Access-Token`,
  `Cookie`, and PII fields (`email`, `phone`, `address`, `customer_name`)
  before emit.

---

## Open questions (Phase 4 backlog)

- Should the Order Board have a muted "fulfiller is picking" indicator?
  Requires a new `status: picking` value + allow-list entry in
  `validators.validate_status`.
- Voice Prompt: should wake-word be gated on tablet presence? Decision
  deferred until fulfiller flow testing.
