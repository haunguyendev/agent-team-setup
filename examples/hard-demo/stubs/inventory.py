"""INVENTORY - implement per README.md. Every public name below is part of the frozen contract."""
from __future__ import annotations


class Inventory:
    def __init__(self, stock: dict) -> None:
        raise NotImplementedError("Inventory.__init__")

    def available(self, sku: str) -> int:
        raise NotImplementedError("Inventory.available")

    def reserved(self, order_id: str) -> dict | None:
        raise NotImplementedError("Inventory.reserved")

    def reserve(self, order_id: str, items: dict) -> bool:
        raise NotImplementedError("Inventory.reserve")

    def release(self, order_id: str) -> bool:
        raise NotImplementedError("Inventory.release")
