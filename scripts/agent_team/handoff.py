#!/usr/bin/env python3
"""Worker/verifier/coordinator entrypoint for the handoff protocol.

    publish --repo MAIN --worktree WORKTREE --task-id ID --attempt N --result FILE --base-commit SHA
    verify  --repo MAIN --task-id ID --attempt N
    promote --repo MAIN --task-id ID --attempt N

Exit codes: 0 = proven, 2 = protocol violation or veto.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.ledger import Ledger  # noqa: E402
from core.protocol import ProtocolError  # noqa: E402
from scripts.agent_team import promote as promoter  # noqa: E402
from scripts.agent_team import store, verify as verifier  # noqa: E402


def _emit(payload: dict, as_json: bool, stream=sys.stdout) -> None:
    if as_json:
        json.dump(payload, stream, indent=2, sort_keys=True)
        stream.write("\n")
    else:
        for key, value in payload.items():
            print(f"{key}: {value}")


def _sync(ledger: Ledger, task_id: str, action) -> None:
    """Ledger writes are coordinator-only and skipped when the task is unknown."""
    if not ledger.path.exists():
        return
    try:
        action(ledger)
    except ProtocolError as error:
        print(f"ledger note: {error}", file=sys.stderr)


def cmd_publish(args: argparse.Namespace) -> int:
    manifest = store.publish(
        repo=Path(args.repo),
        worktree=Path(args.worktree),
        task_id=args.task_id,
        attempt=args.attempt,
        result_path=Path(args.result),
        base_commit=args.base_commit,
        strict_untracked=args.strict_untracked,
    )
    ledger = Ledger(Path(args.repo), args.ledger)
    _sync(ledger, args.task_id, lambda led: led.advance(args.task_id, "working", note="attempt published"))
    _emit(
        {
            "task_id": manifest["task_id"],
            "attempt": manifest["attempt"],
            "head_commit": manifest["head_commit"],
            "patch_sha256": manifest["patch_sha256"],
            "files": len(manifest["files"]),
            "untracked_not_in_patch": manifest["untracked_not_in_patch"],
            "published_to": str(store.attempt_path(Path(args.repo), args.task_id, args.attempt)),
        },
        args.json,
    )
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    record = verifier.verify(
        repo=Path(args.repo),
        task_id=args.task_id,
        attempt=args.attempt,
        timeout=args.timeout,
        rerun=not args.no_rerun,
        verifier=args.verifier,
    )
    ledger = Ledger(Path(args.repo), args.ledger)

    def sync(led: Ledger) -> None:
        if args.task_id not in led.load()["tasks"]:
            raise ProtocolError(f"unknown task {args.task_id}")
        led.advance(args.task_id, "review", note=f"verifier={record['verdict']}")
        if record["verdict"] != "accept":
            led.advance(args.task_id, "revision_required", note="verifier found divergences")

    _sync(ledger, args.task_id, sync)
    _emit(record, args.json)
    return 0 if record["verdict"] == "accept" else 2


def cmd_promote(args: argparse.Namespace) -> int:
    record = promoter.promote(
        repo=Path(args.repo),
        task_id=args.task_id,
        attempt=args.attempt,
        ledger_dir=args.ledger,
        apply_change=not args.no_apply,
        coordinator=args.coordinator,
    )
    _emit(record, args.json)
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    repo = Path(args.repo)
    if args.attempt is not None:
        handoff = store.load_attempt(repo, args.task_id, args.attempt)
        payload = {
            "manifest": handoff["manifest"],
            "marker": handoff["marker"],
            "result": handoff["result"],
            "verification": handoff["verification"],
        }
    else:
        payload = {"attempts": store.list_attempts(repo, args.task_id)}
    _emit(payload, True)
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    _emit({"attempts": store.list_attempts(Path(args.repo))}, args.json)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    def base(target: argparse.ArgumentParser, repo: bool = True) -> None:
        if repo:
            target.add_argument("--repo", required=True, help="coordinator main checkout")
        target.add_argument("--ledger", default="ledger")
        target.add_argument("--json", action="store_true")

    publish = sub.add_parser("publish", help="worker: freeze an attempt as an immutable handoff")
    base(publish)
    publish.add_argument("--worktree", required=True)
    publish.add_argument("--task-id", required=True)
    publish.add_argument("--attempt", type=int, required=True)
    publish.add_argument("--result", required=True, help="path to the result JSON")
    publish.add_argument("--base-commit", required=True)
    publish.add_argument(
        "--strict-untracked",
        action="store_true",
        help="refuse to publish while untracked files exist in the worktree",
    )
    publish.set_defaults(func=cmd_publish)

    check = sub.add_parser("verify", help="verifier: rerun the recorded commands and veto on divergence")
    base(check)
    check.add_argument("--task-id", required=True)
    check.add_argument("--attempt", type=int, required=True)
    check.add_argument("--timeout", type=float, default=600.0)
    check.add_argument("--no-rerun", action="store_true", help="record a verdict without executable evidence")
    check.add_argument("--verifier", default="coordinator")
    check.set_defaults(func=cmd_verify)

    promote = sub.add_parser("promote", help="coordinator: apply a verified attempt to the main checkout")
    base(promote)
    promote.add_argument("--task-id", required=True)
    promote.add_argument("--attempt", type=int, required=True)
    promote.add_argument("--no-apply", action="store_true", help="record the disposition without staging files")
    promote.add_argument("--coordinator", default="coordinator")
    promote.set_defaults(func=cmd_promote)

    show = sub.add_parser("show", help="inspect a published attempt")
    base(show)
    show.add_argument("--task-id", required=True)
    show.add_argument("--attempt", type=int)
    show.set_defaults(func=cmd_show)

    listing = sub.add_parser("list", help="list every published attempt for this repository")
    base(listing)
    listing.set_defaults(func=cmd_list)
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
