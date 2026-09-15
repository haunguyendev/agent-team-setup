"""Immutable handoff store: workers publish, the coordinator consumes.

Layout::

    <root>/<repository-identity>/<task-id>/attempt-<n>/
        result.json      validated worker result
        change.patch     exact diff base_commit..head_commit
        manifest.json    hashes and provenance pointers
        MARKER           digest binding result.json to manifest.json

Attempts are append-only: a retry increments the attempt number and never
overwrites a published attempt. Payload files are written read-only, and every
read re-derives the marker digest so tampering fails closed.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from core.protocol import ProtocolError, atomic_json, repo_identity, validate_result

from . import gitutil, manifest as m

HANDOFF_ENV = m.HANDOFF_ENV
DEFAULT_HANDOFF_ROOT = m.DEFAULT_HANDOFF_ROOT
PROTOCOL_VERSION = m.PROTOCOL_VERSION
PAYLOAD_FILES = m.PAYLOAD_FILES


def handoff_root() -> Path:
    override = os.environ.get(HANDOFF_ENV, "").strip()
    return Path(override).expanduser() if override else DEFAULT_HANDOFF_ROOT


def namespaced_root(repo: Path, root: Path | None = None) -> Path:
    return (root or handoff_root()) / repo_identity(repo)


def attempt_path(repo: Path, task_id: str, attempt: int, root: Path | None = None) -> Path:
    if attempt < 0:
        raise ProtocolError("attempt must be zero or greater")
    return namespaced_root(repo, root) / task_id / f"attempt-{attempt}"


def publish(
    repo: Path,
    worktree: Path,
    task_id: str,
    attempt: int,
    result_path: Path,
    base_commit: str,
    root: Path | None = None,
    strict_untracked: bool = False,
) -> dict[str, Any]:
    """Publish one immutable attempt. Any unprovable precondition raises."""
    repo = repo.resolve()
    worktree = worktree.resolve()
    _check_worktree(repo, worktree, base_commit)
    untracked = gitutil.untracked_files(worktree)
    if untracked and strict_untracked:
        raise ProtocolError(f"worktree has untracked files: {', '.join(untracked)}")

    result = json.loads(Path(result_path).read_text(encoding="utf-8"))
    validate_result(result, task_id)

    target = attempt_path(repo, task_id, attempt, root)
    if target.exists():
        raise ProtocolError(f"attempt {attempt} for {task_id} is already published at {target}")
    target.mkdir(parents=True, exist_ok=False)

    head_commit = gitutil.head_commit(worktree)
    patch = gitutil.patch_bytes(repo, base_commit, head_commit)
    result_bytes = m.canonical(result)
    entry = {
        "protocol_version": PROTOCOL_VERSION,
        "task_id": task_id,
        "attempt": attempt,
        "repository": str(repo),
        "namespace": repo_identity(repo),
        "base_commit": base_commit,
        "head_commit": head_commit,
        "branch": gitutil.current_branch(worktree),
        "worktree": str(worktree),
        "outcome": result["outcome"],
        "agent_model": result["provenance"]["agent_model"],
        "patch_sha256": m.sha256(patch),
        "patch_bytes": len(patch),
        "result_sha256": m.sha256(result_bytes),
        "files": [
            {"path": path, "sha256": gitutil.blob_sha256(repo, head_commit, path)}
            for path in gitutil.changed_files(repo, base_commit, head_commit)
        ],
        "untracked_not_in_patch": untracked,
        "published_at": m.stamp(),
    }
    marker = {
        "digest": m.marker_digest(entry, entry["result_sha256"]),
        "task_id": task_id,
        "attempt": attempt,
        "base_commit": base_commit,
        "head_commit": head_commit,
        "published_at": entry["published_at"],
    }

    (target / "change.patch").write_bytes(patch)
    (target / "result.json").write_bytes(result_bytes)
    atomic_json(target / "manifest.json", entry)
    atomic_json(target / "MARKER", marker)
    for name in PAYLOAD_FILES:
        os.chmod(target / name, 0o444)
    return entry


def _check_worktree(repo: Path, worktree: Path, base_commit: str) -> None:
    if not gitutil.is_git_repo(repo):
        raise ProtocolError(f"{repo} is not a git repository")
    if not gitutil.is_git_repo(worktree):
        raise ProtocolError(f"{worktree} is not a git worktree")
    if gitutil.toplevel(worktree) == gitutil.toplevel(repo):
        raise ProtocolError("worker must publish from an isolated worktree, never from the main checkout")
    if gitutil.common_dir(worktree) != gitutil.common_dir(repo):
        raise ProtocolError("worktree does not share an object store with the target repository")
    if not gitutil.commit_exists(repo, base_commit):
        raise ProtocolError(f"base commit {base_commit} is unknown to {repo}")
    if not gitutil.is_ancestor(repo, base_commit, gitutil.head_commit(worktree)):
        raise ProtocolError("base commit is not an ancestor of the worktree HEAD")
    if gitutil.tracked_changes(worktree).strip():
        raise ProtocolError("worktree has uncommitted changes; commit the attempt before publishing")


def load_attempt(repo: Path, task_id: str, attempt: int, root: Path | None = None) -> dict[str, Any]:
    """Read an attempt and prove it is intact, else raise."""
    target = attempt_path(repo, task_id, attempt, root)
    if not target.is_dir():
        raise ProtocolError(f"no published attempt {attempt} for {task_id} at {target}")
    missing = [name for name in PAYLOAD_FILES if not (target / name).exists()]
    if missing:
        raise ProtocolError(f"handoff is incomplete, missing {', '.join(missing)}")
    try:
        entry = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
        marker = json.loads((target / "MARKER").read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ProtocolError(f"handoff is malformed: {error}") from error
    result_bytes = (target / "result.json").read_bytes()
    if m.sha256(result_bytes) != entry.get("result_sha256"):
        raise ProtocolError("result.json does not match the manifest hash")
    patch = (target / "change.patch").read_bytes()
    if m.sha256(patch) != entry.get("patch_sha256"):
        raise ProtocolError("change.patch does not match the manifest hash")
    if marker.get("digest") != m.marker_digest(entry, entry["result_sha256"]):
        raise ProtocolError("handoff marker digest mismatch; attempt was modified after publication")
    record = {
        "path": target,
        "manifest": entry,
        "marker": marker,
        "result": json.loads(result_bytes.decode("utf-8")),
        "patch": patch,
        "verification": None,
    }
    verification = target / m.VERIFICATION_FILE
    if verification.exists():
        record["verification"] = json.loads(verification.read_text(encoding="utf-8"))
    return record


def write_verification(repo: Path, task_id: str, attempt: int, record: dict[str, Any]) -> Path:
    target = attempt_path(repo, task_id, attempt) / m.VERIFICATION_FILE
    if target.exists():
        raise ProtocolError(f"attempt {attempt} already has a verification verdict; open a new attempt")
    atomic_json(target, record)
    return target


def list_attempts(repo: Path, task_id: str | None = None, root: Path | None = None) -> list[dict[str, Any]]:
    base = namespaced_root(repo, root)
    if not base.is_dir():
        return []
    tasks = [task_id] if task_id else sorted(entry.name for entry in base.iterdir() if entry.is_dir())
    found: list[dict[str, Any]] = []
    for task in tasks:
        task_dir = base / task
        if not task_dir.is_dir():
            continue
        for entry in sorted(task_dir.iterdir()):
            if not entry.is_dir() or not entry.name.startswith("attempt-"):
                continue
            attempt = int(entry.name.split("-", 1)[1])
            item: dict[str, Any] = {"task_id": task, "attempt": attempt, "path": str(entry), "state": "intact"}
            try:
                loaded = load_attempt(repo, task, attempt, root)
            except ProtocolError as error:
                item["state"] = f"damaged: {error}"
                item["verification"] = (entry / m.VERIFICATION_FILE).exists()
                found.append(item)
                continue
            item["outcome"] = loaded["manifest"]["outcome"]
            item["head_commit"] = loaded["manifest"]["head_commit"]
            item["files"] = [record["path"] for record in loaded["manifest"]["files"]]
            item["verification"] = (loaded["verification"] or {}).get("verdict")
            found.append(item)
    return found
