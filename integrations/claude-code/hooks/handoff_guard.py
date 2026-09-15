#!/usr/bin/env python3
"""Write-boundary guard: a worker never writes another checkout.

Registered as a Claude Code PreToolUse hook. Exit code 2 blocks the tool call
and returns the reason to the agent.

Rule enforced: if the session works inside a linked git worktree, every write
must stay inside that worktree. Writes into the coordinator's main checkout (or
a sibling worktree of the same repository) are refused.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}


def _git(cwd: Path, *args: str) -> str | None:
    proc = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True)
    return proc.stdout.strip() if proc.returncode == 0 else None


def _repo_info(path: Path) -> tuple[Path, Path] | None:
    top = _git(path, "rev-parse", "--show-toplevel")
    common = _git(path, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if not top or not common:
        return None
    return Path(top).resolve(), Path(common).resolve()


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    if payload.get("tool_name") not in WRITE_TOOLS:
        return 0
    tool_input = payload.get("tool_input") or {}
    raw_target = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not raw_target:
        return 0
    session = Path(payload.get("cwd") or Path.cwd())
    session_repo = _repo_info(session)
    if session_repo is None:
        return 0
    session_top, session_common = session_repo
    if (session_top / ".git").is_dir():
        return 0  # coordinator checkout: unrestricted
    target = Path(raw_target)
    if not target.is_absolute():
        target = session / target
    target_repo = _repo_info(target.parent if target.parent.exists() else session)
    if target_repo is None:
        return 0
    target_top, target_common = target_repo
    if target_common != session_common or target_top == session_top:
        return 0
    print(
        f"Blocked: this session owns {session_top} and must not write {target_top}. "
        "Publish an immutable handoff instead; only the coordinator promotes changes.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
