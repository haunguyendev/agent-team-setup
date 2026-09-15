#!/usr/bin/env python3
"""Portable CLI: inspect a project adapter, bootstrap a ledger, install the agent wiring."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.ledger import Ledger  # noqa: E402
from core.protocol import ProtocolError, repo_identity  # noqa: E402
from scripts.agent_team import install as installer  # noqa: E402


def cmd_inspect(args: argparse.Namespace) -> int:
    adapter = json.loads(Path(args.adapter).read_text(encoding="utf-8"))
    repo = Path(args.repo or adapter["repository"]).expanduser().resolve()
    actual = dict(adapter)
    actual["repository"] = str(repo)
    actual["repository_exists"] = repo.is_dir()
    actual["repository_identity"] = repo_identity(repo)
    actual["namespace_matches"] = actual["repository_identity"] == adapter.get("handoff_namespace")
    actual["ledger_exists"] = (repo / adapter["ledger"]).is_dir()
    print(json.dumps(actual, indent=2, sort_keys=True))
    return 0 if actual["repository_exists"] and actual["ledger_exists"] else 2


def cmd_init(args: argparse.Namespace) -> int:
    ledger = Ledger(Path(args.repo), args.ledger)
    state = ledger.init(task_title=args.title, overwrite=args.force)
    print(json.dumps({"ledger": str(ledger.root), "namespace": ledger.namespace, "tasks": list(state["tasks"])}, indent=2))
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    print(json.dumps(Ledger(Path(args.repo), args.ledger).summary(), indent=2, sort_keys=True))
    return 0


def cmd_add_task(args: argparse.Namespace) -> int:
    ledger = Ledger(Path(args.repo), args.ledger)
    task = ledger.add_task(args.title, task_id=args.task_id)
    print(json.dumps(ledger.summary(), indent=2, sort_keys=True))
    return 0 if task else 2


def cmd_assign(args: argparse.Namespace) -> int:
    ledger = Ledger(Path(args.repo), args.ledger)
    files = [entry.strip() for entry in args.files.split(",") if entry.strip()]
    task = ledger.assign(
        task_id=args.task_id,
        owner=args.owner,
        attempt=args.attempt,
        files=files,
        base_commit=args.base_commit,
        worktree=args.worktree,
    )
    print(json.dumps(task, indent=2, sort_keys=True))
    return 0


def cmd_transition(args: argparse.Namespace) -> int:
    ledger = Ledger(Path(args.repo), args.ledger)
    task = ledger.advance(args.task_id, args.status, note=args.note)
    print(json.dumps(task, indent=2, sort_keys=True))
    return 0


def cmd_install(args: argparse.Namespace) -> int:
    if args.global_scope:
        args.scope = "user"
    payload = installer.install(
        repo=Path(args.repo),
        scope=args.scope,
        target=args.target,
        with_hooks=args.with_hooks,
        with_agents_md=args.with_agents_md,
        force=args.force,
    )
    payload["snippet_content"] = Path(payload["agents_snippet"]).read_text(encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    inspect = sub.add_parser("inspect", help="resolve an adapter against a checkout")
    inspect.add_argument("--adapter", required=True)
    inspect.add_argument("--repo", help="override the adapter repository path")
    inspect.set_defaults(func=cmd_inspect)

    init = sub.add_parser("init", help="bootstrap the coordinator ledger in a project")
    init.add_argument("--repo", required=True)
    init.add_argument("--ledger", default="ledger")
    init.add_argument("--title", help="seed the first task")
    init.add_argument("--force", action="store_true")
    init.set_defaults(func=cmd_init)

    status = sub.add_parser("status", help="print the compact ledger state")
    status.add_argument("--repo", required=True)
    status.add_argument("--ledger", default="ledger")
    status.set_defaults(func=cmd_status)

    add_task = sub.add_parser("add-task", help="add a task to the queue")
    add_task.add_argument("--repo", required=True)
    add_task.add_argument("--ledger", default="ledger")
    add_task.add_argument("--title", required=True)
    add_task.add_argument("--task-id")
    add_task.set_defaults(func=cmd_add_task)

    assign = sub.add_parser("assign", help="assign a task with exclusive file ownership")
    assign.add_argument("--repo", required=True)
    assign.add_argument("--ledger", default="ledger")
    assign.add_argument("--task-id", required=True)
    assign.add_argument("--owner", required=True)
    assign.add_argument("--attempt", type=int, required=True)
    assign.add_argument("--files", required=True, help="comma-separated exclusive ownership")
    assign.add_argument("--base-commit", required=True)
    assign.add_argument("--worktree")
    assign.set_defaults(func=cmd_assign)

    transition = sub.add_parser("transition", help="move a task to a legal status")
    transition.add_argument("--repo", required=True)
    transition.add_argument("--ledger", default="ledger")
    transition.add_argument("--task-id", required=True)
    transition.add_argument("--status", required=True, choices=("pending", "assigned", "working", "review", "approved", "complete", "revision_required", "blocked", "unmeasured", "rejected"))
    transition.add_argument("--note")
    transition.set_defaults(func=cmd_transition)

    install = sub.add_parser("install", help="install skills/subagents/commands into a coding agent")
    install.add_argument("--repo", required=True)
    install.add_argument("--scope", choices=("project", "user"), default="project")
    install.add_argument(
        "--target",
        choices=("auto", "claude", "omp", "both"),
        default="auto",
        help="which agent harness to wire up; auto installs OMP only where OMP already exists",
    )
    install.add_argument("--global", dest="global_scope", action="store_true", help="alias for --scope user")
    install.add_argument("--with-hooks", action="store_true", help="add the write-boundary hook (backup first)")
    install.add_argument("--with-agents-md", action="store_true", help="copy the AGENTS.md snippet locally")
    install.add_argument("--force", action="store_true")
    install.set_defaults(func=cmd_install)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        return args.func(args)
    except ProtocolError as error:
        print(f"protocol violation: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
