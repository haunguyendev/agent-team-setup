"""Order orchestration: quote, reserve, cancel. Idempotent per order id."""
from __future__ import annotations

import pricing


class OrderService:
    def __init__(self, inventory) -> None:
        self.inventory = inventory
        self._orders: dict[str, dict] = {}

    def create(self, order_id: str, lines: list, coupon: dict | None = None) -> dict:
        if order_id in self._orders:
            return self._orders[order_id]
        quoted = pricing.quote(lines, coupon)
        items = {line["sku"]: line["quantity"] for line in lines}
        reserved = self.inventory.reserve(order_id, items)
        order = {
            "order_id": order_id,
            "quote": quoted,
            "reserved": reserved,
            "status": "confirmed" if reserved else "backorder",
        }
        self._orders[order_id] = order
        return order

    def cancel(self, order_id: str) -> bool:
        order = self._orders.get(order_id)
        if order is None or order["status"] == "cancelled":
            return False
        released = self.inventory.release(order_id) if order["reserved"] else False
        order["status"] = "cancelled"
        if released:
            order["reserved"] = False
        return True

    def get(self, order_id: str) -> dict | None:
        return self._orders.get(order_id)
