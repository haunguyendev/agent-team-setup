"""Money rules. All amounts are integer đồng; rounding is half-up on exact ties."""
from __future__ import annotations


def _half_up(numerator: int, denominator: int) -> int:
    return (numerator * 2 + denominator) // (2 * denominator)


def line_total(line: dict) -> int:
    quantity = line["quantity"]
    unit_price = line["unit_price"]
    if not isinstance(quantity, int) or isinstance(quantity, bool) or not 1 <= quantity <= 99:
        raise ValueError("quantity must be an integer between 1 and 99")
    if not isinstance(unit_price, int) or isinstance(unit_price, bool) or unit_price < 0:
        raise ValueError("unit_price must be a non-negative integer")
    return unit_price * quantity


def subtotal(lines: list) -> int:
    if not lines:
        raise ValueError("an order needs at least one line")
    return sum(line_total(line) for line in lines)


def tier_discount(amount: int) -> int:
    for threshold, percent in ((2_000_000, 15), (1_000_000, 10), (500_000, 5)):
        if amount >= threshold:
            return _half_up(amount * percent, 100)
    return 0


def apply_coupon(amount: int, coupon: dict | None) -> int:
    if coupon is None:
        return amount
    kind, value = coupon.get("type"), coupon.get("value")
    if kind == "percent":
        if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 100:
            raise ValueError("percent coupon value must be between 1 and 100")
        return amount - _half_up(amount * value, 100)
    if kind == "fixed":
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError("fixed coupon value must be a non-negative integer")
        return amount - min(value, amount)
    raise ValueError(f"unknown coupon type: {kind!r}")


def shipping_fee(payable: int) -> int:
    return 0 if payable >= 300_000 else 25_000


def quote(lines: list, coupon: dict | None = None) -> dict:
    gross = subtotal(lines)
    tier = tier_discount(gross)
    after_tier = gross - tier
    after_coupon = apply_coupon(after_tier, coupon)
    shipping = shipping_fee(after_coupon)
    return {
        "subtotal": gross,
        "tier_discount": tier,
        "coupon_discount": after_tier - after_coupon,
        "shipping": shipping,
        "total": after_coupon + shipping,
    }
