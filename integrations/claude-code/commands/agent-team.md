---
description: Run an objective as a ledger-coordinated agent team (coordinator + workers + verifier)
argument-hint: <objective>
---

Objective: $ARGUMENTS

Act as the coordinator for this objective using the `agent-team-ledger` skill.

1. Resolve `$P` from `.claude/agent-team-ledger/protocol-root.txt` (or `$AGENT_TEAM_ROOT`).
2. If `ledger/tasks.json` does not exist yet:
   `python "$P/scripts/agent_team.py" init --repo "$(git rev-parse --show-toplevel)" --title "<objective>"`.
3. Write the plan and seed 3-6 tasks, then show the queue with
   `python "$P/scripts/agent_team.py" status --repo "$(git rev-parse --show-toplevel)"`.
4. For each task: create an isolated worktree, dispatch the `agent-team-worker` subagent with only
   the curated inputs plus its single task, then dispatch `agent-team-verifier`.
5. Promote only on an `accept` verdict, from a clean main checkout:
   `python "$P/scripts/agent_team/handoff.py" promote --repo MAIN --task-id <TASK> --attempt <N>`.
6. Finish with `python "$P/scripts/agent_team/reconcile.py" --repo MAIN --json` and report ledger
   facts: task ids, attempts, verdicts, staged files, and anything left unverified.

Never mark a task complete from a worker's own summary, a timeout, or an idle event.
