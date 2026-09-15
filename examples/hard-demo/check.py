#!/usr/bin/env python3
"""Acceptance check for the Bát Cơm order engine. Exit 0 only when README.md is satisfied.

    python3 check.py            # every section
    python3 check.py pricing    # one section, for a single owned module
"""
from __future__ import annotations

import sys
import threading
import traceback

FAILURES: list[str] = []


def expect(label: str, actual, wanted) -> None:
    if actual != wanted:
        FAILURES.append(f"{label}: expected {wanted!r}, got {actual!r}")


def expect_raises(label: str, call, kind: type = ValueError) -> None:
    try:
        call()
    except kind:
        return
    except Exception as error:  # noqa: BLE001 - the point is to report the wrong type
        FAILURES.append(f"{label}: raised {type(error).__name__}, expected {kind.__name__}")
    else:
        FAILURES.append(f"{label}: no exception, expected {kind.__name__}")


def run_section(name: str, check) -> None:
    """Run one section; a crash inside it is a failure, not a stopped run."""
    try:
        check()
    except Exception:  # noqa: BLE001 - report and continue with the other sections
        FAILURES.append(f"{name}: crashed - {traceback.format_exc().strip().splitlines()[-1]}")


TIE_5 = [{"unit_price": 166_670, "quantity": 3}]  # 500.010d, 5% -> 25.000,5d
TIE_10 = [{"unit_price": 333_335, "quantity": 3}]  # 1.000.005d, 10% -> 100.000,5d
AT_THRESHOLD = [{"unit_price": 100_000, "quantity": 3}]  # exactly 300.000d
UNDER = [{"unit_price": 99_999, "quantity": 3}]  # 299.997d


def pricing_section() -> None:
    import pricing

    expect("subtotal", pricing.subtotal(TIE_5), 500_010)
    expect("tier below 500k", pricing.tier_discount(499_999), 0)
    expect("tier at 500k", pricing.tier_discount(500_000), 25_000)
    expect("tier at 999_999", pricing.tier_discount(999_999), 50_000)
    expect("tier at 1M", pricing.tier_discount(1_000_000), 100_000)
    expect("tier at 1_999_999", pricing.tier_discount(1_999_999), 200_000)
    expect("tier at 2M", pricing.tier_discount(2_000_000), 300_000)

    expect("half-up tie at 5%", pricing.quote(TIE_5)["tier_discount"], 25_001)
    expect("half-up tie at 10%", pricing.quote(TIE_10)["tier_discount"], 100_001)

    percent = pricing.quote(TIE_5, {"type": "percent", "value": 10})
    expect("percent coupon applies after the tier", percent["coupon_discount"], 47_501)
    expect("percent coupon total", percent["total"], 427_508)

    capped = pricing.quote(TIE_5, {"type": "fixed", "value": 999_999})
    expect("fixed coupon caps at the payable amount", capped["coupon_discount"], 475_009)
    expect("a free order still pays shipping", capped["shipping"], 25_000)
    expect("free order total", capped["total"], 25_000)

    expect("shipping free at the threshold", pricing.quote(AT_THRESHOLD)["shipping"], 0)
    expect("shipping charged below it", pricing.quote(UNDER)["shipping"], 25_000)
    expect("under-threshold total", pricing.quote(UNDER)["total"], 324_997)

    expect_raises("quantity 0", lambda: pricing.quote([{"unit_price": 1_000, "quantity": 0}]))
    expect_raises("quantity 100", lambda: pricing.quote([{"unit_price": 1_000, "quantity": 100}]))
    expect_raises("quantity as string", lambda: pricing.quote([{"unit_price": 1_000, "quantity": "2"}]))
    expect_raises("negative price", lambda: pricing.quote([{"unit_price": -1, "quantity": 1}]))
    expect_raises("empty order", lambda: pricing.quote([]))
    expect_raises("unknown coupon type", lambda: pricing.quote(AT_THRESHOLD, {"type": "bogus", "value": 1}))
    expect_raises("percent coupon 0", lambda: pricing.quote(AT_THRESHOLD, {"type": "percent", "value": 0}))
    expect_raises("percent coupon 101", lambda: pricing.quote(AT_THRESHOLD, {"type": "percent", "value": 101}))


def inventory_section() -> None:
    import inventory

    stock = {"cat-food": 3}
    held = inventory.Inventory(stock)
    expect("available", held.available("cat-food"), 3)
    expect("unknown sku is empty", held.available("gold-leaf"), 0)

    expect("first reserve", held.reserve("A", {"cat-food": 2}), True)
    expect("available after reserve", held.available("cat-food"), 1)
    expect("all-or-nothing refusal", held.reserve("B", {"cat-food": 2}), False)
    expect("refusal changes nothing", held.available("cat-food"), 1)
    expect("unknown sku refuses", held.reserve("C", {"gold-leaf": 1}), False)

    expect("reserve is idempotent", held.reserve("A", {"cat-food": 2}), True)
    expect("idempotence does not double count", held.available("cat-food"), 1)
    expect("reserved view", held.reserved("A"), {"cat-food": 2})

    expect("release", held.release("A"), True)
    expect("stock restored", held.available("cat-food"), 3)
    expect("second release is a no-op", held.release("A"), False)
    expect("unknown release is a no-op", held.release("Z"), False)
    expect("no drift after no-ops", held.available("cat-food"), 3)
    expect("caller's dict is not mutated", stock, {"cat-food": 3})

    copy_check = inventory.Inventory({"cat-food": 3})
    copy_check.reserve("D", {"cat-food": 2})
    view = copy_check.reserved("D") or {}
    view["cat-food"] = 999
    expect("reserved() hands out a copy", copy_check.reserved("D"), {"cat-food": 2})

    churn = inventory.Inventory({"chew-toy": 5})
    for index in range(200):
        churn.reserve(f"C{index}", {"chew-toy": 2})
        churn.release(f"C{index}")
    expect("no drift after reserve/release churn", churn.available("chew-toy"), 5)

    # Sound but incomplete: a correct implementation can only ever let one thread win, and never
    # oversell. A lock-free implementation may still pass this by luck on CPython.
    last_one = inventory.Inventory({"last-unit": 1})
    winners: list[bool] = []
    gate = threading.Barrier(16)

    def compete(index: int) -> None:
        gate.wait()
        winners.append(last_one.reserve(f"R{index}", {"last-unit": 1}))

    threads = [threading.Thread(target=compete, args=(index,)) for index in range(16)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    expect("no double spend in a thread burst", winners.count(True), 1)
    expect("stock never goes negative", last_one.available("last-unit"), 0)


def orders_section() -> None:
    import inventory
    import orders

    held = inventory.Inventory({"cat-food": 5})
    service = orders.OrderService(held)
    line = [{"sku": "cat-food", "unit_price": 166_670, "quantity": 2}]

    first = service.create("O1", line)
    expect("confirmed status", first["status"], "confirmed")
    expect("reserved flag", first["reserved"], True)
    expect("order total", first["quote"]["total"], 333_340)
    expect("stock after reserve", held.available("cat-food"), 3)

    again = service.create("O1", line)
    expect("create is idempotent", again["quote"]["total"], first["quote"]["total"])
    expect("idempotence does not reserve twice", held.available("cat-food"), 3)
    expect("get returns the order", service.get("O1")["status"], "confirmed")

    too_much = [{"sku": "cat-food", "unit_price": 100_000, "quantity": 4}]
    expect("backorder status", service.create("O2", too_much)["status"], "backorder")
    expect("backorder reserves nothing", held.available("cat-food"), 3)

    expect("cancel", service.cancel("O1"), True)
    expect("cancel restores stock", held.available("cat-food"), 5)
    expect("second cancel is a no-op", service.cancel("O1"), False)
    expect("cancelled status", service.get("O1")["status"], "cancelled")
    expect("unknown order", service.get("O9"), None)

    coupon_order = service.create("O3", line, {"type": "percent", "value": 10})
    expect("coupon reaches the order", coupon_order["quote"]["coupon_discount"], 33_334)


SECTIONS = {"pricing": pricing_section, "inventory": inventory_section, "orders": orders_section}


def main() -> int:
    wanted = sys.argv[1] if len(sys.argv) > 1 else "all"
    if wanted != "all" and wanted not in SECTIONS:
        print(f"unknown section {wanted!r}; use all, {', '.join(SECTIONS)}")
        return 2
    for name, check in SECTIONS.items():
        if wanted in ("all", name):
            run_section(name, check)

    if FAILURES:
        print(f"FAIL ({len(FAILURES)})")
        for index, failure in enumerate(FAILURES, start=1):
            print(f"  {index}. {failure}")
        return 1
    print(f"PASS - {wanted} meets the brief")
    return 0


if __name__ == "__main__":
    sys.exit(main())
