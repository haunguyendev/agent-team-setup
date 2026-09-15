"""Human-readable ledger files: scaffolding and bounded curation.

These files are the coordinator's working memory for agents: `task.md` keeps the
original request, `plan.md` the strategy, `notes.md` the insight that must
survive into the next fresh context. They are size-capped so the ledger cannot
quietly turn into a transcript.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .protocol import ProtocolError

LEDGER_FILES = ("task.md", "plan.md", "notes.md", "PROGRESS.md")
LEDGER_DIRS = ("promotions", "locks")
PLAN_LIMIT = 4000
NOTES_LIMIT = 8000
PLACEHOLDER = "# {name}\n\nempty; the coordinator curates this file.\n"


def scaffold(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for name in LEDGER_DIRS:
        (root / name).mkdir(exist_ok=True)
    for name in LEDGER_FILES:
        target = root / name
        if not target.exists():
            target.write_text(PLACEHOLDER.format(name=name[:-3]), encoding="utf-8")


def initial_state(repository: str, namespace: str, created_at: str) -> dict[str, Any]:
    return {
        "version": 1,
        "protocol_version": 1,
        "repository": repository,
        "namespace": namespace,
        "created_at": created_at,
        "tasks": {},
    }


def append_bounded(path: Path, text: str, limit: int) -> int:
    current = path.read_text(encoding="utf-8") if path.exists() else ""
    body = text.strip()
    updated = f"{current.rstrip()}\n{body}\n" if current.strip() else f"{body}\n"
    if len(updated) > limit:
        raise ProtocolError(f"{path.name} would exceed {limit} characters; curate it first")
    path.write_text(updated, encoding="utf-8")
    return len(updated)


def append_progress(root: Path, stamp: str, text: str) -> None:
    with (root / "PROGRESS.md").open("a", encoding="utf-8") as stream:
        stream.write(f"- {stamp} {text}\n")
