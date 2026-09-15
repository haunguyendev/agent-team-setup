# Bát Cơm order engine

Three modules, one frozen contract. `check.py` is the specification made executable, and it is
**read-only for every worker**: changing it is out of scope, and the verifier rejects an attempt that
touches it.

## Money rules (`pricing.py`)

- All money is an integer number of đồng. No floats in any stored or returned value.
- Line total = `unit_price * quantity`. Quantity must be an integer in `1..99` and `unit_price` a
  non-negative integer; anything else raises `ValueError`. An order needs at least one line.
- Subtotal = sum of line totals.
- Tier discount on the subtotal: `>= 2_000_000` → 15%, `>= 1_000_000` → 10%, `>= 500_000` → 5%,
  otherwise 0.
- Rounding is **half-up on exact ties**: `25_000,5` → `25_001`, never banker's rounding.
- Coupons:
  - `{"type": "percent", "value": 1..100}` → half-up percentage of the amount **after** the tier
    discount;
  - `{"type": "fixed", "value": n}` → discount `min(n, amount)`.
  - An unknown type, a percent of 0 or more than 100, or a non-integer value raises `ValueError`.
- Shipping: free when the payable amount (after tier and coupon) is `>= 300_000`, else `25_000`.
  A free order still pays shipping.
- `quote(lines, coupon=None)` returns
  `{"subtotal", "tier_discount", "coupon_discount", "shipping", "total"}`.

## Stock rules (`inventory.py`)

- `Inventory(stock)` must not mutate the caller's dict; `available(sku)` returns 0 for unknown skus.
- `reserve(order_id, items)` is all-or-nothing across the whole basket, idempotent per order id (a
  second call for the same id returns `True` and deducts nothing), and safe for concurrent use.
- `release(order_id)` restores stock exactly once: the second call returns `False` and changes nothing.
- `reserved(order_id)` returns a copy of what that order holds, or `None`.

## Order rules (`orders.py`)

- `OrderService(inventory).create(order_id, lines, coupon=None)` quotes, reserves, and returns
  `{"order_id", "quote", "reserved", "status"}`, where status is `confirmed` when the reservation
  succeeded and `backorder` otherwise. A backorder must reserve nothing.
- `create` is idempotent per order id: the second call returns the first result and does not reserve
  again.
- `cancel(order_id)` releases a reservation, marks the order `cancelled`, and returns `True`; the
  second cancel returns `False`. `get(order_id)` returns `None` for an unknown order.

## Language constraints

- Must run on the repository's `python3` (3.9 here) with the standard library only.
- No third-party dependencies, no pytest: `check.py` is the whole harness.
- Use `from __future__ import annotations` when you annotate with `X | None`.

## Ownership and acceptance

| Task | Owns | Acceptance command |
| --- | --- | --- |
| T-001 | `pricing.py` | `python3 check.py pricing` |
| T-002 | `inventory.py` | `python3 check.py inventory` |
| T-003 | `orders.py` | `python3 check.py orders` |

The final gate is `python3 check.py` (all sections). `orders.py` imports both other modules, so T-003
only makes sense once T-001 and T-002 are promoted.

On concurrency: `check.py` runs a 16-thread burst against a single unit and asserts that no more than
one reservation wins and that stock never goes negative. That check is sound but incomplete - it
cannot prove lock-freedom on CPython, so reason about the interleaving yourself rather than trusting a
green run.
