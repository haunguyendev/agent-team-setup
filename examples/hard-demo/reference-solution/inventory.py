"""Stock reservations. All-or-nothing per order, idempotent per order id, thread-safe."""
from __future__ import annotations

import threading


class Inventory:
    def __init__(self, stock: dict[str, int]) -> None:
        self._lock = threading.Lock()
        self._stock = dict(stock)
        self._reserved: dict[str, dict[str, int]] = {}

    def available(self, sku: str) -> int:
        with self._lock:
            return self._stock.get(sku, 0)

    def reserved(self, order_id: str) -> dict[str, int] | None:
        with self._lock:
            held = self._reserved.get(order_id)
            return dict(held) if held else None

    def reserve(self, order_id: str, items: dict[str, int]) -> bool:
        with self._lock:
            if order_id in self._reserved:
                return True
            for sku, quantity in items.items():
                if quantity <= 0 or self._stock.get(sku, 0) < quantity:
                    return False
            for sku, quantity in items.items():
                self._stock[sku] = self._stock.get(sku, 0) - quantity
            self._reserved[order_id] = dict(items)
            return True

    def release(self, order_id: str) -> bool:
        with self._lock:
            held = self._reserved.pop(order_id, None)
            if not held:
                return False
            for sku, quantity in held.items():
                self._stock[sku] = self._stock.get(sku, 0) + quantity
            return True
