# Script contract

The canonical core lives in `core/`; repository adapters identify paths and project rules.
Each repository may retain a compatibility copy of `scripts/agent_team/handoff.py` so a worker can invoke
the protocol without importing code from another project. The local copies must implement:

```text
publish --repo MAIN --worktree WORKTREE --task-id ID --attempt N --result FILE --base-commit SHA
verify  --repo MAIN --task-id ID --attempt N
promote --repo MAIN --task-id ID --attempt N       # coordinator, from MAIN only
```

The handoff root defaults to `~/.claude-camel/handoffs` and can be overridden with
`CLAUDE_AGENT_HANDOFF_ROOT`. It is namespaced by the canonical repository path hash.

`reconcile.py --repo MAIN` reports worktrees, unmerged commits, and handoff attempts without
deleting anything.

## Implemented entrypoints

```bash
# worker (from its own worktree; fails closed on any unprovable precondition)
python3 scripts/agent_team/handoff.py publish --repo MAIN --worktree WT --task-id T-001 \
  --attempt 0 --result /tmp/T-001.json --base-commit SHA [--strict-untracked] [--json]

# verifier: reruns the recorded commands against the recorded head commit
python3 scripts/agent_team/handoff.py verify --repo MAIN --task-id T-001 --attempt 0 \
  [--timeout 600] [--no-rerun] [--verifier NAME] [--json]     # exit 0 accept, exit 2 reject

# coordinator: apply a verified attempt to a clean main checkout
python3 scripts/agent_team/handoff.py promote --repo MAIN --task-id T-001 --attempt 0 \
  [--no-apply] [--coordinator NAME] [--json]

python3 scripts/agent_team/handoff.py show --repo MAIN --task-id T-001 [--attempt 0]
python3 scripts/agent_team/handoff.py list --repo MAIN [--json]
python3 scripts/agent_team/reconcile.py --repo MAIN [--stale-hours 24] [--json]

# coordinator ledger and agent wiring
python3 scripts/agent_team.py init       --repo MAIN --title "objective"
python3 scripts/agent_team.py add-task   --repo MAIN --title "…" [--task-id T-002]
python3 scripts/agent_team.py assign     --repo MAIN --task-id T-001 --owner worker-a \
  --attempt 0 --files app.py,lib/x.py --base-commit SHA [--worktree ../wt-T-001]
python3 scripts/agent_team.py transition --repo MAIN --task-id T-001 --status blocked --note "…"
python3 scripts/agent_team.py status     --repo MAIN
python3 scripts/agent_team.py install    --repo MAIN [--scope project|user] [--with-hooks] [--with-agents-md]
```

Exit codes: `0` proven, `2` protocol violation or verifier veto. Attempts are immutable; a retry
increments the attempt number. Commands are rerun without a shell, and a command that fails vetoes
promotion unless it is recorded with `expected_failure: true`.

Inspect an adapter with:

`python scripts/agent_team.py inspect --adapter adapters/metatrader_5_exness.json`

For a different checkout, pass `--repo PROJECT_ROOT`; the adapter's project rules and
protocol version remain reusable without editing the core. The adapter's pinned
`handoff_namespace` belongs to its original checkout, so `inspect` reports `namespace_matches`
for the checkout you supplied; handoffs are always namespaced by the resolved repository path.

All adapters use 20 logical lanes and the `auto` model. Backend throttling changes retry
eligibility, never lane identity or the configured logical lane count.
