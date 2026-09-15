"""Fail-closed git helpers.

Every helper raises :class:`GitError` instead of returning a sentinel, because
the protocol treats "cannot prove it" the same as "not proven".
"""
from __future__ import annotations

import subprocess
from pathlib import Path


class GitError(RuntimeError):
    """Raised when a git query fails or an invariant cannot be proven."""


def _run(repo: Path, args: list[str], text: bool) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=text,
        check=False,
    )


def git(repo: Path, *args: str) -> str:
    proc = _run(repo, list(args), True)
    if proc.returncode != 0:
        raise GitError(f"git {' '.join(args)} failed ({proc.returncode}): {proc.stderr.strip()}")
    return proc.stdout


def git_bytes(repo: Path, *args: str) -> bytes:
    proc = _run(repo, list(args), False)
    if proc.returncode != 0:
        raise GitError(
            f"git {' '.join(args)} failed ({proc.returncode}): {proc.stderr.decode('utf-8', 'replace').strip()}"
        )
    return proc.stdout


def toplevel(path: Path) -> Path:
    return Path(git(path, "rev-parse", "--show-toplevel").strip()).resolve()


def is_git_repo(path: Path) -> bool:
    if not path.is_dir():
        return False
    proc = _run(path, ["rev-parse", "--show-toplevel"], True)
    return proc.returncode == 0


def common_dir(path: Path) -> Path:
    raw = git(path, "rev-parse", "--path-format=absolute", "--git-common-dir").strip()
    return Path(raw).resolve()


def is_main_worktree(path: Path) -> bool:
    """True only for the primary checkout, never for a linked worktree."""
    git_pointer = path.resolve() / ".git"
    return git_pointer.is_dir()


def head_commit(path: Path) -> str:
    return git(path, "rev-parse", "HEAD").strip()


def commit_exists(repo: Path, commit: str) -> bool:
    proc = _run(repo, ["cat-file", "-e", f"{commit}^{{commit}}"], True)
    return proc.returncode == 0


def is_ancestor(repo: Path, ancestor: str, descendant: str) -> bool:
    proc = _run(repo, ["merge-base", "--is-ancestor", ancestor, descendant], True)
    return proc.returncode == 0


def status_porcelain(path: Path) -> str:
    return git(path, "status", "--porcelain")


def status_porcelain(path: Path, ignore: tuple[str, ...] = (), untracked: bool = True) -> str:
    args = ["status", "--porcelain"]
    if not untracked:
        args.append("--untracked-files=no")
    if ignore:
        args += ["--", "."] + [f":(exclude){entry}" for entry in ignore]
    return git(path, *args)


def tracked_changes(path: Path, ignore: tuple[str, ...] = ()) -> str:
    """Uncommitted changes to tracked files; untracked scratch files are excluded."""
    return status_porcelain(path, ignore, untracked=False)


def has_tracked_changes(path: Path, ignore: tuple[str, ...] = ()) -> bool:
    return bool(tracked_changes(path, ignore).strip())


def untracked_files(path: Path) -> list[str]:
    raw = git(path, "ls-files", "--others", "--exclude-standard")
    return [line for line in raw.splitlines() if line.strip()]


def is_clean(path: Path, ignore: tuple[str, ...] = ()) -> bool:
    """Uncommitted source changes make a checkout dirty.

    Coordinator-owned paths (the ledger) are excluded because the coordinator
    rewrites them continuously and they are not part of a promotion.
    """
    args = ["status", "--porcelain"]
    if ignore:
        args += ["--", "."] + [f":(exclude){entry}" for entry in ignore]
    return not git(path, *args).strip()


def current_branch(path: Path) -> str:
    return git(path, "rev-parse", "--abbrev-ref", "HEAD").strip()


def changed_files(repo: Path, base: str, head: str) -> list[str]:
    raw = git(repo, "diff", "--name-only", "--no-renames", base, head)
    return [line for line in raw.splitlines() if line.strip()]


def patch_bytes(repo: Path, base: str, head: str) -> bytes:
    return git_bytes(repo, "diff", "--binary", "--no-color", "--full-index", base, head)


def blob_sha256(repo: Path, commit: str, path: str) -> str:
    import hashlib

    content = git_bytes(repo, "show", f"{commit}:{path}")
    return hashlib.sha256(content).hexdigest()


def worktrees(repo: Path) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    entry: dict[str, str] = {}
    for line in git(repo, "worktree", "list", "--porcelain").splitlines():
        if not line.strip():
            if entry:
                out.append(entry)
            entry = {}
            continue
        key, _, value = line.partition(" ")
        entry[key] = value
    if entry:
        out.append(entry)
    return out


def commits_ahead(repo: Path, ref: str, base: str = "HEAD") -> list[str]:
    raw = git(repo, "rev-list", "--no-merges", f"{base}..{ref}")
    return [line for line in raw.splitlines() if line.strip()]
