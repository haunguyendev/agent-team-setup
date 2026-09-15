"""Project-neutral, fail-closed coordination primitives.

The repository adapters may add paths and domain rules, but they must use these
identity, provenance, and atomic-write invariants.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

OUTCOMES = {"DONE", "BLOCKED", "UNMEASURED", "NO SAFE CHANGE"}


class ProtocolError(ValueError):
    """Raised when a coordination artifact violates the protocol."""


def repo_identity(repo: Path) -> str:
    return hashlib.sha256(str(repo.resolve()).encode("utf-8")).hexdigest()[:20]


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def _nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_result(result: Any, task_id: str) -> dict[str, Any]:
    if not isinstance(result, dict):
        raise ProtocolError("result must be an object")
    if result.get("task_id") != task_id:
        raise ProtocolError("result task_id mismatch")
    if result.get("outcome") not in OUTCOMES:
        raise ProtocolError("result outcome is invalid")
    if not _nonempty_string(result.get("plain_summary")):
        raise ProtocolError("result plain_summary is required")
    provenance = result.get("provenance")
    if not isinstance(provenance, dict):
        raise ProtocolError("result provenance is required")
    for field in ("base_commit", "agent_model"):
        if not _nonempty_string(provenance.get(field)):
            raise ProtocolError(f"provenance.{field} is required")
    if not isinstance(provenance.get("files_symbols"), list) or not provenance["files_symbols"]:
        raise ProtocolError("provenance.files_symbols must be non-empty")
    commands = provenance.get("commands")
    if not isinstance(commands, list) or not commands:
        raise ProtocolError("provenance.commands must be non-empty")
    for command in commands:
        if not isinstance(command, dict) or not _nonempty_string(command.get("cmd")):
            raise ProtocolError("each command needs a cmd")
        if not isinstance(command.get("exit"), int) or isinstance(command.get("exit"), bool):
            raise ProtocolError("each command needs an integer exit")
    for field in ("tests", "findings", "uncertainty"):
        if not isinstance(provenance.get(field), list):
            raise ProtocolError(f"provenance.{field} must be a list")
    return result
