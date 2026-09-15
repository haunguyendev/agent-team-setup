## Agent team protocol (ledger-based self-orchestration)

Applies to any coding agent that can run shell commands. The canonical runtime is this package;
resolve `PROTOCOL` to its path with `$AGENT_TEAM_ROOT`, else from `agent-team-ledger/protocol-root.txt`
under the agent config directory (`.claude/` for Claude Code, `.omp/agent/` or `.omp/` for OMP).

Roles, and who may write what:

| Role | Owns | Never |
|---|---|---|
| Coordinator | `ledger/`, promotion, merges | a worker worktree |
| Worker | one linked git worktree and one attempt | the main checkout, sibling worktrees, the ledger |
| Verifier | verdicts only | source, ledger |

Rules:

1. The ledger is authoritative; chat text, idle events, timeouts, and self-reported success are
   not evidence. Lifecycle: `pending → assigned → working → review → approved → complete`, with
   `revision_required`, `blocked`, `unmeasured`, `rejected` as explicit failure states.
2. Workers publish immutable handoffs; only the coordinator promotes them:
   `python "$PROTOCOL/scripts/agent_team/handoff.py" publish --repo MAIN --worktree WT --task-id T --attempt N --result FILE --base-commit SHA`.
   Attempts are append-only; a retry increments the attempt number.
3. Verify before promoting:
   `python "$PROTOCOL/scripts/agent_team/handoff.py" verify --repo MAIN --task-id T --attempt N`.
   The verifier reruns the recorded commands against the recorded head commit; any divergence
   vetoes promotion.
4. Promote only from a clean main checkout whose `HEAD` descends from the recorded base commit:
   `python "$PROTOCOL/scripts/agent_team/handoff.py" promote --repo MAIN --task-id T --attempt N`.
5. Parallel workers must have exclusive file ownership or be read-only. Promotion and merge are
   coordinator-serialized.
6. Ledger files stay bounded: `plan.md` ≤ 4000 characters, `notes.md` ≤ 8000. Store evidence in
   the handoff and keep only summaries and pointers in the ledger.
7. Before cleanup, record worktree path, branch, base and current commit, dirty files, handoff
   status, and review disposition. Reconciliation is read-only.
8. Reconcile with `python "$PROTOCOL/scripts/agent_team/reconcile.py" --repo MAIN --json`.

Project safety, build, and deploy gates always remain in force; the protocol never overrides them.
