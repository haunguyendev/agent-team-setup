---
description: Run an objective as a ledger-coordinated agent team (coordinator + workers + verifier)
argument-hint: <objective / ý tưởng, Vietnamese or English>
---

Objective: $ARGUMENTS

You are the coordinator. **Reply in the user's language** and keep your own messages short: ledger
facts (task id, attempt, verdict, staged files), not narration.

0. Resolve `$P` from `.claude/agent-team-ledger/protocol-root.txt` (or `$AGENT_TEAM_ROOT`).
1. Orient first, read-only:
   - `git rev-parse --show-toplevel` - use that absolute path in every command
   - the repo brief: `README.md`, `CLAUDE.md`, `AGENTS.md`, `docs/` - whatever states the requirements
   - the existing acceptance command: `check.py`, `tests/`, `Makefile`, scripts in `package.json`
   - `python3 "$P/scripts/agent_team.py" status --repo REPO`
2. Ledger:
   - if `ledger/tasks.json` exists, reuse its pending tasks and map the objective onto them; do not
     create a duplicate queue
   - otherwise `init --repo REPO --title "<objective>"`, then add 1-3 tasks
   - write 3-6 sentences into `ledger/plan.md` (<= 4000 characters)
3. An acceptance command is mandatory - the verifier needs something executable:
   - use the repo's existing check/test command when there is one
   - otherwise the task itself must add one (a script or test that fails before the change and
     passes after)
   - never accept a task whose evidence is "it looks right"
4. For each ready task: `assign` with exclusive file ownership, create the worktree, spawn
   `agent-team-worker`, then spawn `agent-team-verifier`. Report the verdict with its numbered
   reasons verbatim.
5. Promote only on `accept`, from a clean main checkout. Then re-run the acceptance command in the
   main checkout and paste the output.
6. Finish with `status` and `reconcile --json`: what is complete, what is blocked, what is unverified.

Never: write a file the worker owns, mark a task complete from a worker's summary, widen scope, edit
`ledger/tasks.json` by hand, or hide a refusal.
