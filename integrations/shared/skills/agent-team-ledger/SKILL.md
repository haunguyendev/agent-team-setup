---
name: agent-team-ledger
description: Run coding work as a ledger-coordinated agent team - fresh worker contexts, immutable handoffs, external verification, and a coordinator-owned ledger. Use when a task is large enough to split across worktrees, when the user asks for agent teams / parallel workers / a verifier, or when a worker result must be promoted into the main checkout only after executable proof.
---

# Agent team ledger

Ledger-based self-orchestration: one model, several fresh contexts, durable curated state,
and a verifier whose executable result vetoes a confident report. Roles are prompts, not
different models.

## Locate the protocol root

```bash
# $P = the protocol package root; run once per session
P="${AGENT_TEAM_ROOT:-$(cat .claude/agent-team-ledger/protocol-root.txt 2>/dev/null \
  || cat .omp/agent/agent-team-ledger/protocol-root.txt 2>/dev/null \
  || cat .omp/agent-team-ledger/protocol-root.txt 2>/dev/null)}"
[ -n "$P" ] || echo "protocol root not found - run the package's install.sh"
```

Never edit `$P/core` or `$P/scripts` mid-task.

## Dispatch

- **Claude Code**: `Task` tool with `subagent_type: agent-team-worker`.
- **OMP**: `task` tool with `agent: "agent-team-worker"`; put several items in one `tasks[]` batch for
  parallel workers, and `isolated: true` requests a worktree.

On both harnesses a spawned worker keeps the coordinator's working directory unless you start it in
the worktree, so name the absolute worktree path in every dispatch and do not rely on the guard hook
to separate the two.

## Roles and who may write what

| Role | Owns | Must never |
|---|---|---|
| Coordinator | `ledger/` (`task.md`, `plan.md`, `tasks.json`, `notes.md`, `PROGRESS.md`, `promotions/`), promotion, merges | edit worker worktrees |
| Worker | one linked worktree and its current attempt | write the main checkout or a sibling worktree |
| Verifier | verdicts only (`verification.json` inside the handoff) | edit source or the ledger |

`handoff_guard.py` enforces the worker boundary as a `PreToolUse` hook when installed
with `--with-hooks`.

## Lifecycle

`pending → assigned → working → review → approved → complete`
Failure states: `revision_required`, `blocked`, `unmeasured`, `rejected`.
A timeout, rate limit, context overflow, idle event, or malformed output is never success.
Retries increment the attempt number; published attempts are immutable.

## Coordinator loop

```bash
python "$P/scripts/agent_team.py" init --repo MAIN --title "one-line objective"
python "$P/scripts/agent_team.py" status --repo MAIN
python "$P/scripts/agent_team/handoff.py" list --repo MAIN --json
python "$P/scripts/agent_team/handoff.py" promote --repo MAIN --task-id T-001 --attempt 0
python "$P/scripts/agent_team/reconcile.py" --repo MAIN --json
```

Rules:
- Re-curate the queue after every result: merge duplicates, close finished tasks, then assign
  exactly one next task with exclusive file ownership.
- Derive the acceptance command from repo conventions before assigning (`README.md` for the brief,
  `check.py` / `tests/` / `Makefile` for the check). If none exists, the task must add one: the
  verifier needs a command that fails before the change and passes after it.
- Keep `plan.md` under 4000 and `notes.md` under 8000 characters; the ledger holds pointers,
  never transcripts.
- Assign with `assign`, which writes a lock identifying repository, task, attempt, owner, files,
  and base commit:

```bash
python "$P/scripts/agent_team.py" add-task --repo MAIN --title "…" [--task-id T-002]
python "$P/scripts/agent_team.py" assign --repo MAIN --task-id T-001 --owner worker-a \
  --attempt 0 --files app.py,lib/x.py --base-commit "$BASE" --worktree ../wt-T-001
python "$P/scripts/agent_team.py" transition --repo MAIN --task-id T-001 --status blocked --note "…"
```
- Promote from the main checkout only, only after `verify` returned `accept`.
- Treat `merge-base --is-ancestor` and a clean main checkout as preconditions, not suggestions.

## Worker loop

```bash
git -C MAIN worktree add ../wt-T-001 -b agent/T-001 <base_commit>
# ... edit only inside ../wt-T-001, run the task's own checks ...
git -C ../wt-T-001 add -A && git -C ../wt-T-001 commit -m "T-001: <what>"
python "$P/scripts/agent_team/handoff.py" publish \
  --repo MAIN --worktree ../wt-T-001 --task-id T-001 --attempt 0 \
  --result /tmp/T-001-result.json --base-commit <base_commit>
```

The result JSON must satisfy `$P/schemas/result.schema.json`:

```json
{
  "task_id": "T-001",
  "outcome": "DONE",
  "plain_summary": "one paragraph, no hedging",
  "provenance": {
    "base_commit": "sha",
    "agent_model": "auto",
    "files_symbols": ["path.py:Symbol"],
    "commands": [{"cmd": "python -m pytest tests/x.py -q", "exit": 0}],
    "tests": [], "findings": [], "uncertainty": []
  }
}
```

- `commands` are rerun verbatim by the verifier, without a shell (no `&&`, pipes, or redirects -
  wrap compound work in a script). Record the real exit code; never record a command you did not
  run.
- A command that fails vetoes promotion even when you recorded it honestly. If a non-zero exit is
  the intended baseline, mark that entry `"expected_failure": true`.
- Publish requires committed tracked files: commit first. Publish is all-or-nothing and refuses to
  overwrite an existing attempt.
- Untracked scratch files (caches, logs) are allowed; they are listed in `manifest.json` under
  `untracked_not_in_patch` so nothing is dropped silently. `--strict-untracked` refuses them.
- `NO SAFE CHANGE` is a valid outcome; do not invent a patch to look productive.

## Verifier loop

```bash
python "$P/scripts/agent_team/handoff.py" verify --repo MAIN --task-id T-001 --attempt 0 --json
```

Exit `0` = accept, exit `2` = reject with numbered reasons. The verifier checks out the
recorded head commit in a throwaway detached worktree, reruns every recorded command without a
shell, and records any divergence. Missing executables, timeouts, shell metacharacters, and
failing commands are divergences, not passes - a failing command vetoes unless it is recorded
with `expected_failure: true`. Do not "fix" a reject by lowering the bar - open a new attempt.

## Anti-patterns

- Trusting a worker's `plain_summary` or a chat message as proof of completion.
- Rerunning an attempt in place, overwriting `result.json`, or editing `MARKER`.
- Letting a worker write the ledger or the main checkout.
- Freezing a wrong plan into `notes.md` without a fresh-perspective worker when anchoring risk
  is high.
