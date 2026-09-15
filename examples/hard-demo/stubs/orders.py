"""ORDERS - implement per README.md. Every public name below is part of the frozen contract."""
from __future__ import annotations


class OrderService:
    def __init__(self, inventory) -> None:
        raise NotImplementedError("OrderService.__init__")

    def create(self, order_id: str, lines: list, coupon: dict | None = None) -> dict:
        raise NotImplementedError("OrderService.create")

    def cancel(self, order_id: str) -> bool:
        raise NotImplementedError("OrderService.cancel")

    def get(self, order_id: str) -> dict | None:
        raise NotImplementedError("OrderService.get")
