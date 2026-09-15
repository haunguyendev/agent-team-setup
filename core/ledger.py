"""Durable, coordinator-owned task state.

The ledger is the authoritative state. Chat messages, idle events, timeouts and
worker self-reports never change it; only explicit coordinator transitions do.
`tasks.json` is a queue, not a transcript.
"""
from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path
from typing import Any

from .ledger_files import (
    NOTES_LIMIT,
    PLAN_LIMIT,
    append_bounded,
    append_progress,
    initial_state,
    scaffold,
)
from .protocol import ProtocolError, atomic_json, repo_identity
from .task_states import FAILURE, HISTORY_LIMIT, TRANSITIONS, route, validate_status


def _stamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class Ledger:
    """Coordinator-owned ledger rooted at ``<repo>/<ledger_dir>``."""

    def __init__(self, repo: Path, ledger_dir: str = "ledger") -> None:
        self.repo = repo.resolve()
        self.root = self.repo / ledger_dir
        self.path = self.root / "tasks.json"
        self.namespace = repo_identity(self.repo)

    # -- lifecycle ---------------------------------------------------------
    def init(self, task_title: str | None = None, overwrite: bool = False) -> dict[str, Any]:
        if self.path.exists() and not overwrite:
            raise ProtocolError("ledger already initialised")
        scaffold(self.root)
        state = initial_state(str(self.repo), self.namespace, _stamp())
        if task_title:
            state["tasks"]["T-001"] = self._new_task("T-001", task_title)
        atomic_json(self.path, state)
        return state

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            raise ProtocolError(f"no ledger at {self.path}")
        try:
            state = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise ProtocolError(f"ledger tasks.json is malformed: {error}") from error
        if not isinstance(state, dict) or not isinstance(state.get("tasks"), dict):
            raise ProtocolError("ledger tasks.json is malformed")
        return state

    # -- mutations ---------------------------------------------------------
    def add_task(self, title: str, task_id: str | None = None, **fields: Any) -> dict[str, Any]:
        state = self.load()
        identifier = task_id or self._next_id(state)
        if identifier in state["tasks"]:
            raise ProtocolError(f"task {identifier} already exists")
        if not isinstance(title, str) or not title.strip():
            raise ProtocolError("task title is required")
        state["tasks"][identifier] = self._new_task(identifier, title, **fields)
        atomic_json(self.path, state)
        return state["tasks"][identifier]

    def assign(
        self,
        task_id: str,
        owner: str,
        attempt: int,
        files: list[str],
        base_commit: str,
        worktree: str | None = None,
    ) -> dict[str, Any]:
        """pending/revision_required → assigned, writing a task lock."""
        if not owner.strip() or not base_commit.strip():
            raise ProtocolError("owner and base_commit are required for assignment")
        if not files:
            raise ProtocolError("assignment needs exclusive file ownership")
        state = self.load()
        self._task(state, task_id)
        lock = {
            "repository": str(self.repo),
            "task": task_id,
            "attempt": attempt,
            "owner": owner,
            "files": list(files),
            "base_commit": base_commit,
            "worktree": worktree,
            "issued_at": _stamp(),
        }
        state = self._set_status(state, task_id, "assigned", note=f"owner={owner} attempt={attempt}")
        state["tasks"][task_id].update(
            {
                "owner": owner,
                "attempt": attempt,
                "files": list(files),
                "base_commit": base_commit,
                "worktree": worktree,
                "lock": lock,
            }
        )
        atomic_json(self.path, state)
        atomic_json(self.root / "locks" / f"{task_id}-{attempt}.json", lock)
        return state["tasks"][task_id]

    def transition(self, task_id: str, status: str, note: str | None = None, **fields: Any) -> dict[str, Any]:
        state = self.load()
        state = self._set_status(state, task_id, status, note=note)
        self._apply_fields(state, task_id, fields)
        atomic_json(self.path, state)
        return state["tasks"][task_id]

    def advance(self, task_id: str, target: str, note: str | None = None, **fields: Any) -> dict[str, Any]:
        """Move to ``target`` through the shortest legal path, one recorded step at a time."""
        state = self.load()
        current = self._task(state, task_id)["status"]
        for index, step in enumerate(route(current, target, task_id)):
            state = self._set_status(state, task_id, step, note=note if index == 0 else None)
        self._apply_fields(state, task_id, fields)
        atomic_json(self.path, state)
        return state["tasks"][task_id]

    def record_promotion(self, task_id: str, attempt: int, record: dict[str, Any]) -> Path:
        path = self.root / "promotions" / f"{task_id}-{attempt}.json"
        if path.exists():
            raise ProtocolError(f"promotion record already exists: {path}")
        atomic_json(path, record)
        return path

    def append_note(self, text: str, limit: int = NOTES_LIMIT) -> int:
        return append_bounded(self.root / "notes.md", text, limit)

    def append_plan(self, text: str) -> int:
        return append_bounded(self.root / "plan.md", text, PLAN_LIMIT)

    def append_progress(self, text: str) -> None:
        append_progress(self.root, _stamp(), text)

    # -- read-only views ---------------------------------------------------
    def summary(self) -> dict[str, Any]:
        state = self.load()
        tasks = state["tasks"]
        counts = Counter(task["status"] for task in tasks.values())
        return {
            "repository": state["repository"],
            "namespace": state["namespace"],
            "counts": dict(sorted(counts.items())),
            "queue": [self._compact(task) for task in tasks.values() if task["status"] != "complete"],
            "attention": [self._compact(task) for task in tasks.values() if task["status"] in FAILURE],
        }

    # -- internals ---------------------------------------------------------
    def _new_task(self, identifier: str, title: str, **fields: Any) -> dict[str, Any]:
        task = {
            "id": identifier,
            "title": title.strip(),
            "status": "pending",
            "owner": None,
            "attempt": 0,
            "files": [],
            "base_commit": None,
            "worktree": None,
            "handoff": None,
            "verification": None,
            "promotion": None,
            "created_at": _stamp(),
            "updated_at": _stamp(),
            "history": [{"status": "pending", "at": _stamp()}],
        }
        task.update(fields)
        return task

    @staticmethod
    def _next_id(state: dict[str, Any]) -> str:
        taken = {int(key.split("-")[1]) for key in state["tasks"] if key.startswith("T-")}
        return f"T-{max(taken, default=0) + 1:03d}"

    @staticmethod
    def _task(state: dict[str, Any], task_id: str) -> dict[str, Any]:
        if task_id not in state["tasks"]:
            raise ProtocolError(f"unknown task {task_id}")
        return state["tasks"][task_id]

    @staticmethod
    def _apply_fields(state: dict[str, Any], task_id: str, fields: dict[str, Any]) -> None:
        state["tasks"][task_id].update({key: value for key, value in fields.items() if value is not None})

    def _set_status(self, state: dict[str, Any], task_id: str, status: str, note: str | None = None) -> dict[str, Any]:
        task = self._task(state, task_id)
        validate_status(status)
        if status not in TRANSITIONS[task["status"]]:
            raise ProtocolError(f"illegal transition {task['status']} → {status} for {task_id}")
        task["status"] = status
        task["updated_at"] = _stamp()
        entry = {"status": status, "at": _stamp()}
        if note:
            entry["note"] = note
        task["history"] = (task["history"] + [entry])[-HISTORY_LIMIT:]
        return state

    @staticmethod
    def _compact(task: dict[str, Any]) -> dict[str, Any]:
        keys = ("id", "title", "status", "owner", "attempt", "files", "worktree", "handoff")
        return {key: task.get(key) for key in keys}
