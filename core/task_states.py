"""Task lifecycle graph.

Kept separate from the ledger's I/O so the legal transitions can be read and
tested on their own. Every transition is explicit: no state may be reached
implicitly from a chat message, idle event, or timeout.
"""
from __future__ import annotations

from .protocol import ProtocolError

LIFECYCLE = ("pending", "assigned", "working", "review", "approved", "complete")
FAILURE = ("revision_required", "blocked", "unmeasured", "rejected")
STATUSES = LIFECYCLE + FAILURE

TRANSITIONS: dict[str, tuple[str, ...]] = {
    "pending": ("assigned", "blocked", "rejected"),
    "assigned": ("working", "revision_required", "blocked", "rejected"),
    "working": ("review", "revision_required", "blocked", "unmeasured", "rejected"),
    "review": ("approved", "revision_required", "rejected", "unmeasured"),
    "approved": ("complete", "revision_required"),
    "revision_required": ("assigned", "blocked", "rejected"),
    "unmeasured": ("assigned", "blocked", "rejected"),
    "blocked": ("assigned", "rejected"),
    "rejected": ("assigned",),
    "complete": (),
}

HISTORY_LIMIT = 20


def validate_status(status: str) -> str:
    if status not in STATUSES:
        raise ProtocolError(f"unknown status {status}")
    return status


def route(current: str, target: str, task_id: str) -> list[str]:
    """Shortest legal path from ``current`` to ``target``; empty when already there."""
    validate_status(current)
    validate_status(target)
    if current == target:
        return []
    seen = {current}
    frontier = [(current, [])]
    while frontier:
        status, path = frontier.pop(0)
        for step in TRANSITIONS[status]:
            if step == target:
                return path + [step]
            if step not in seen:
                seen.add(step)
                frontier.append((step, path + [step]))
    raise ProtocolError(f"no legal path from {current} to {target} for {task_id}")
