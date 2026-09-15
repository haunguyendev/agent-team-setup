"""PRICING - implement per README.md. Every public name below is part of the frozen contract."""
from __future__ import annotations


def subtotal(lines: list) -> int:
    raise NotImplementedError("pricing.subtotal")


def tier_discount(amount: int) -> int:
    raise NotImplementedError("pricing.tier_discount")


def apply_coupon(amount: int, coupon: dict | None) -> int:
    raise NotImplementedError("pricing.apply_coupon")


def shipping_fee(payable: int) -> int:
    raise NotImplementedError("pricing.shipping_fee")


def quote(lines: list, coupon: dict | None = None) -> dict:
    raise NotImplementedError("pricing.quote")
