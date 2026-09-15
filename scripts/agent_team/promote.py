"""Coordinator promotion: apply a verified attempt to the main checkout.

Promotion is serialized on the coordinator. A verifier verdict of ``reject``
vetoes promotion outright, and the main checkout must be clean and share history
with the recorded base commit.
"""
from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Any

from core.ledger import Ledger
from core.protocol import ProtocolError

from . import gitutil, store


def _stamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _apply(repo: Path, patch: bytes) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), "apply", "--3way", "--index", "--whitespace=nowarn", "-"],
        input=patch,
        capture_output=True,
    )
    if proc.returncode != 0:
        raise ProtocolError(f"git apply failed: {proc.stderr.decode('utf-8', 'replace').strip()}")
    return gitutil.git(repo, "diff", "--cached", "--name-only").strip()


def promote(
    repo: Path,
    task_id: str,
    attempt: int,
    ledger_dir: str = "ledger",
    apply_change: bool = True,
    coordinator: str = "coordinator",
) -> dict[str, Any]:
    repo = repo.resolve()
    if not gitutil.is_main_worktree(repo):
        raise ProtocolError("promotion must run from the main checkout, not a linked worktree")
    handoff = store.load_attempt(repo, task_id, attempt)
    manifest = handoff["manifest"]
    verification = handoff["verification"]
    if not verification:
        raise ProtocolError("attempt has no verification verdict; run verify first")
    if verification.get("verdict") != "accept":
        raise ProtocolError(f"verifier vetoed attempt {attempt}: {'; '.join(verification.get('reasons', []))}")
    if verification.get("patch_sha256") != manifest["patch_sha256"]:
        raise ProtocolError("verification does not cover this patch")
    if gitutil.has_tracked_changes(repo, ignore=(ledger_dir,)):
        raise ProtocolError(
            "main checkout has uncommitted tracked changes; the coordinator promotes from a clean tree"
        )
    if not gitutil.is_ancestor(repo, manifest["base_commit"], "HEAD"):
        raise ProtocolError("recorded base commit is not an ancestor of the main checkout")

    staged = ""
    if apply_change:
        staged = _apply(repo, handoff["patch"])
        if not staged:
            raise ProtocolError("patch applied nothing; refusing to record an empty promotion")

    record = {
        "task_id": task_id,
        "attempt": attempt,
        "base_commit": manifest["base_commit"],
        "head_commit": manifest["head_commit"],
        "patch_sha256": manifest["patch_sha256"],
        "verification_verdict": verification["verdict"],
        "verification_digest": verification.get("handoff_marker_digest"),
        "files": [entry["path"] for entry in manifest["files"]],
        "staged_files": staged.splitlines(),
        "coordinator": coordinator,
        "promoted_at": _stamp(),
    }

    ledger = Ledger(repo, ledger_dir)
    if ledger.path.exists():
        record_path = ledger.record_promotion(task_id, attempt, record)
        ledger.advance(
            task_id,
            "complete",
            note=f"promoted attempt {attempt} after verifier={verification['verdict']}",
            promotion=str(record_path),
        )
        ledger.append_progress(f"promoted {task_id} attempt {attempt} ({len(record['staged_files'])} files staged)")
    else:
        from core.protocol import atomic_json

        record_path = store.attempt_path(repo, task_id, attempt) / "promotion.json"
        atomic_json(record_path, record)

    record["record_path"] = str(record_path)
    return record
