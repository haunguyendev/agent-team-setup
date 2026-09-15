#!/usr/bin/env python3
"""Read-only reconciliation. Reports; never deletes, never rewrites."""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.ledger import Ledger  # noqa: E402
from core.protocol import repo_identity  # noqa: E402
from scripts.agent_team import gitutil, store  # noqa: E402


def report(repo: Path, ledger_dir: str = "ledger", stale_hours: float = 24.0) -> dict:
    repo = repo.resolve()
    payload: dict = {
        "repository": str(repo),
        "namespace": repo_identity(repo),
        "handoff_root": str(store.handoff_root()),
        "worktrees": [],
        "unmerged_commits": [],
        "attempts": [],
        "stale_attempts": [],
        "ledger": None,
    }
    if gitutil.is_git_repo(repo):
        main_head = gitutil.head_commit(repo)
        for entry in gitutil.worktrees(repo):
            path = Path(entry.get("worktree", ""))
            info = {
                "path": str(path),
                "branch": entry.get("branch", "").replace("refs/heads/", "") or "detached",
                "head": entry.get("HEAD", ""),
                "main": gitutil.is_main_worktree(path) if path.is_dir() else False,
                "exists": path.is_dir(),
                "dirty": None,
            }
            if path.is_dir():
                info["dirty"] = not gitutil.is_clean(path)
                ahead = gitutil.commits_ahead(repo, entry["HEAD"], main_head)
                if ahead:
                    payload["unmerged_commits"].append({"worktree": str(path), "commits": ahead})
            payload["worktrees"].append(info)

    payload["attempts"] = store.list_attempts(repo)
    now = time.time()
    for attempt in payload["attempts"]:
        marker = Path(attempt["path"]) / "MARKER"
        if not marker.exists():
            payload["stale_attempts"].append({**attempt, "reason": "marker missing"})
            continue
        if attempt["state"] != "intact":
            payload["stale_attempts"].append({**attempt, "reason": attempt["state"]})
            continue
        age_hours = (now - marker.stat().st_mtime) / 3600.0
        if age_hours > stale_hours and not attempt.get("verification"):
            payload["stale_attempts"].append(
                {**attempt, "reason": f"unverified for {age_hours:.1f}h"}
            )

    ledger = Ledger(repo, ledger_dir)
    if ledger.path.exists():
        payload["ledger"] = ledger.summary()
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--ledger", default="ledger")
    parser.add_argument("--stale-hours", type=float, default=24.0)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    payload = report(Path(args.repo), args.ledger, args.stale_hours)
    if args.json:
        json.dump(payload, sys.stdout, indent=2, sort_keys=True, default=str)
        sys.stdout.write("\n")
    else:
        print(f"repository: {payload['repository']}")
        for entry in payload["worktrees"]:
            print(f"  worktree {entry['path']} [{entry['branch']}] dirty={entry['dirty']}")
        for group in payload["unmerged_commits"]:
            print(f"  unmerged in {group['worktree']}: {len(group['commits'])} commit(s)")
        for attempt in payload["attempts"]:
            print(f"  handoff {attempt['task_id']} attempt-{attempt['attempt']}: {attempt['state']} verify={attempt.get('verification')}")
        for attempt in payload["stale_attempts"]:
            print(f"  attention {attempt['task_id']} attempt-{attempt['attempt']}: {attempt['reason']}")
        if payload["ledger"]:
            print(f"  ledger counts: {payload['ledger']['counts']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
