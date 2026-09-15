"""Independent verification: rerun the worker's exact commands.

A verifier's executable result vetoes a confident model report. Commands run in
a throwaway detached checkout of the worker's head commit; the main checkout is
never mutated.
"""
from __future__ import annotations

import shlex
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from core.protocol import ProtocolError

from . import gitutil, store

SHELL_CHARS = set("|&;<>$`\n")
OUTPUT_TAIL = 2000


def _stamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def rerun_commands(commands: list[dict[str, Any]], cwd: Path, timeout: float) -> list[dict[str, Any]]:
    """Run each recorded command without a shell; divergence is recorded, never hidden."""
    outcomes: list[dict[str, Any]] = []
    for command in commands:
        raw = str(command.get("cmd", "")).strip()
        claimed = command.get("exit")
        entry: dict[str, Any] = {"cmd": raw, "claimed_exit": claimed, "actual_exit": None, "divergence": None}
        if not raw:
            entry["divergence"] = "empty command"
            outcomes.append(entry)
            continue
        if SHELL_CHARS & set(raw):
            entry["divergence"] = "command needs a shell; refusing to interpret it"
            outcomes.append(entry)
            continue
        argv = shlex.split(raw)
        try:
            proc = subprocess.run(argv, cwd=str(cwd), capture_output=True, text=True, timeout=timeout)
        except FileNotFoundError:
            entry["actual_exit"] = 127
            entry["divergence"] = f"executable not found: {argv[0]}"
            outcomes.append(entry)
            continue
        except subprocess.TimeoutExpired:
            entry["divergence"] = f"timed out after {timeout:g}s"
            outcomes.append(entry)
            continue
        entry["actual_exit"] = proc.returncode
        entry["stdout_tail"] = proc.stdout[-OUTPUT_TAIL:]
        entry["stderr_tail"] = proc.stderr[-OUTPUT_TAIL:]
        entry["expected_failure"] = bool(command.get("expected_failure"))
        if not isinstance(claimed, int) or isinstance(claimed, bool):
            entry["divergence"] = "claimed exit is missing or not an integer"
        elif proc.returncode != claimed:
            entry["divergence"] = f"claimed exit {claimed}, observed {proc.returncode}"
        elif proc.returncode != 0 and not entry["expected_failure"]:
            entry["divergence"] = (
                f"command failed with exit {proc.returncode}; "
                "mark it expected_failure to record a known-bad baseline"
            )
        outcomes.append(entry)
    return outcomes


def verify(
    repo: Path,
    task_id: str,
    attempt: int,
    timeout: float = 600.0,
    rerun: bool = True,
    verifier: str = "coordinator",
) -> dict[str, Any]:
    repo = repo.resolve()
    handoff = store.load_attempt(repo, task_id, attempt)
    manifest = handoff["manifest"]
    commands = handoff["result"]["provenance"]["commands"]
    reasons: list[str] = []
    results: list[dict[str, Any]] = []

    head_commit = manifest["head_commit"]
    if not gitutil.commit_exists(repo, head_commit):
        reasons.append(f"{head_commit[:12]} is not present in {repo}; the attempt is not verifiable here")
    elif not rerun:
        reasons.append("commands were not rerun; the verifier produced no executable evidence")

    if rerun and not reasons:
        checkout = Path(tempfile.mkdtemp(prefix="agent-team-verify-"))
        worktree = checkout / "checkout"
        added = False
        try:
            gitutil.git(repo, "worktree", "add", "--detach", "--force", str(worktree), head_commit)
            added = True
            results = rerun_commands(commands, worktree, timeout)
        finally:
            if added:
                try:
                    gitutil.git(repo, "worktree", "remove", "--force", str(worktree))
                except gitutil.GitError:
                    pass
            shutil.rmtree(checkout, ignore_errors=True)
        for entry in results:
            if entry["divergence"]:
                reasons.append(f"`{entry['cmd']}`: {entry['divergence']}")

    verdict = "accept" if not reasons else "reject"
    record = {
        "task_id": task_id,
        "attempt": attempt,
        "verdict": verdict,
        "reasons": [f"{index + 1}. {reason}" for index, reason in enumerate(reasons)],
        "patch_sha256": manifest["patch_sha256"],
        "head_commit": head_commit,
        "handoff_marker_digest": handoff["marker"]["digest"],
        "commands": results,
        "verifier": verifier,
        "verified_at": _stamp(),
    }
    store.write_verification(repo, task_id, attempt, record)
    return record


def load_verification(repo: Path, task_id: str, attempt: int) -> dict[str, Any]:
    record = store.load_attempt(repo, task_id, attempt)["verification"]
    if not record:
        raise ProtocolError(f"attempt {attempt} of {task_id} has no verification verdict yet")
    return record
