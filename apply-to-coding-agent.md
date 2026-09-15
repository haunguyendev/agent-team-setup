# Applying this package to a coding agent

How to put the ledger protocol in front of a real coding agent (Claude Code, Codex, or anything
that can run shell commands), and how to keep it honest afterwards.

- [What already exists](#what-already-exists)
- [1. Choose the target checkout](#1-choose-the-target-checkout)
- [2. Bootstrap the ledger](#2-bootstrap-the-ledger)
- [3. Install the agent wiring](#3-install-the-agent-wiring)
- [4. Run one task end to end](#4-run-one-task-end-to-end)
- [5. Recover and audit](#5-recover-and-audit)
- [Knobs, limits, gotchas](#knobs-limits-gotchas)
- [Evidence](#evidence)

## What already exists

`core/` (identity, provenance validation, atomic writes, lane journal) plus `adapters/` and the
inspection CLI were already here. The runtime the other documents promise now exists too:

| Entrypoint | Purpose |
|---|---|
| `scripts/agent_team.py` | `inspect`, `init`, `status`, `add-task`, `assign`, `transition`, `install` |
| `scripts/agent_team/handoff.py` | `publish`, `verify`, `promote`, `show`, `list` |
| `scripts/agent_team/reconcile.py` | read-only recovery report |
| `integrations/claude-code/` | skill, three subagents, slash command, write-boundary hook |
| `integrations/agents-md/AGENTS.snippet.md` | agent-neutral rules block for `AGENTS.md`/`CLAUDE.md` |

Nothing here trains a model or changes your agent binary: roles are prompts over fresh contexts,
and the ledger is plain files.

## 1. Choose the target checkout

```bash
P=/path/to/agent-team-setup
python3 "$P/scripts/agent_team.py" inspect --adapter "$P/adapters/promete_verba.json"
python3 "$P/scripts/agent_team.py" inspect --adapter "$P/adapters/promete_verba.json" --repo ~/Developer/promete_verba
```

`inspect` is read-only and exits `2` when the checkout or its ledger is missing. It reports
`namespace_matches`, which compares the adapter's pinned `handoff_namespace` with the identity
derived from the checkout you passed. Adapters pin the namespace of their original checkout, so on
a different machine the namespace differs - that is expected, not a failure. Handoffs are
namespaced by the *actual* repository path at runtime:

```
namespace = sha256(str(repo.resolve()))[:20]
```

Consequences worth knowing: moving or renaming a checkout orphans its previous handoffs, and
`resolve()` follows symlinks (on macOS `/home` is an autofs mount, so `/home/x` resolves to
`/System/Volumes/Data/home/x`). Point the tooling at the real path and stay there.

The default handoff store is `~/.claude-camel/handoffs`; override it with
`CLAUDE_AGENT_HANDOFF_ROOT`. Keep it outside the repository so handoffs survive checkout cleanup.

## 2. Bootstrap the ledger

```bash
cd /path/to/target-repo
python3 "$P/scripts/agent_team.py" init --repo . --title "one-line objective"
python3 "$P/scripts/agent_team.py" add-task --repo . --title "flip the retry policy"
python3 "$P/scripts/agent_team.py" status --repo .
```

`init` creates `ledger/{task.md,plan.md,tasks.json,notes.md,PROGRESS.md,promotions/,locks/}`.
`tasks.json` is the authoritative queue; `plan.md` is capped at 4000 characters and `notes.md` at
8000, so the ledger cannot silently become a transcript. Decide once whether `ledger/` is
committed (shared audit trail) or ignored (local control plane) - both work, but promotion treats
`ledger/` as coordinator-owned either way.

## 3. Install the agent wiring

```bash
python3 "$P/scripts/agent_team.py" install --repo . --scope project --with-hooks --with-agents-md
```

Project scope writes into `<repo>/.claude/`; user scope writes into `~/.claude/` for every project.
Existing files are kept unless you pass `--force`.

| Installed | Contract |
|---|---|
| `skills/agent-team-ledger/SKILL.md` | role table, lifecycle, exact commands, anti-patterns |
| `agents/agent-team-coordinator.md` | owns ledger, promotion, merges |
| `agents/agent-team-worker.md` | one worktree, one attempt, publish |
| `agents/agent-team-verifier.md` | reruns commands, issues verdict |
| `commands/agent-team.md` | `/agent-team <objective>` |
| `hooks/handoff_guard.py` | blocks a worker from writing the main checkout or a sibling worktree |
| `agent-team-ledger/protocol-root.txt` | absolute path to this package, so skills resolve `$P` |
| `settings.json` (with `--with-hooks`) | registers the guard on `Write\|Edit\|MultiEdit\|NotebookEdit`; backup written first |

`--with-agents-md` copies `AGENTS.snippet.md` next to the skill; paste it into the repository
`AGENTS.md`/`CLAUDE.md` so agents that do not read Claude Code skills still follow the protocol.
The snippet is deliberately short: roles, write boundaries, and the five commands that matter.

For Codex or another agent, install with `--scope project`, then paste the snippet. The protocol
itself is agent-agnostic - only the skill/subagent/hook files are Claude Code specific.

## 4. Run one task end to end

Coordinator assigns with exclusive file ownership (`--files` is the lock):

```bash
BASE=$(git rev-parse HEAD)
python3 "$P/scripts/agent_team.py" assign --repo . --task-id T-001 \
  --owner worker-a --attempt 0 --files app.py --base-commit "$BASE" --worktree ../wt-T-001
git worktree add ../wt-T-001 -b agent/T-001 "$BASE"
```

Worker (or the `agent-team-worker` subagent) edits **only** `../wt-T-001`, runs its own checks,
commits, and writes a result satisfying `schemas/result.schema.json`:

```bash
git -C ../wt-T-001 add -A && git -C ../wt-T-001 commit -m "T-001: flip retry policy"
python3 "$P/scripts/agent_team/handoff.py" publish --repo . --worktree ../wt-T-001 \
  --task-id T-001 --attempt 0 --result /tmp/T-001-result.json --base-commit "$BASE" --json
```

`publish` refuses to run unless: the worktree is not the main checkout, it shares the object store,
the base commit is a known ancestor of the worktree `HEAD`, the result validates, tracked files are
committed, and the attempt is not already published. It then freezes `result.json`,
`change.patch`, `manifest.json` (per-file sha256 + patch digest) and `MARKER` (a digest binding the
two) as read-only files. Retries increment `--attempt`; published attempts never change.

Verifier reruns the recorded commands against the recorded head commit in a throwaway detached
worktree:

```bash
python3 "$P/scripts/agent_team/handoff.py" verify --repo . --task-id T-001 --attempt 0 --json
```

Exit `0` = `accept`, exit `2` = `reject` with numbered reasons. Vetoes: patch/marker hash mismatch,
missing head commit, claimed exit different from observed, a command that failed (unless it is
marked `expected_failure`, which is how a legitimately known-bad baseline is recorded), a command
that needs a shell, an executable that does not exist, or a timeout. A timeout is never a pass.

Coordinator promotes from a clean main checkout, serially:

```bash
python3 "$P/scripts/agent_team/handoff.py" promote --repo . --task-id T-001 --attempt 0 --json
```

Promotion requires a stored `accept` verdict whose patch digest matches, no uncommitted tracked
changes outside `ledger/`, and a `HEAD` descended from the recorded base commit. It applies the
patch with `git apply --3way --index`, writes `ledger/promotions/T-001-0.json`, advances the task
to `complete` through legal transitions, and stages (never commits) the files so your own hooks,
build, and deploy gates still run.

## 5. Recover and audit

```bash
python3 "$P/scripts/agent_team/reconcile.py" --repo . --json
```

Reports worktrees with branch/head/dirty state, commits present in a worktree but not in `HEAD`,
every handoff with its integrity state (`intact` or `damaged: ...`), and stale attempts. It never
deletes or rewrites anything. `handoff.py show` dumps a single attempt; `handoff.py list` lists all
of them.

Failure states stay explicit: `revision_required`, `blocked`, `unmeasured`, `rejected`. A worker
that stops, times out, hits a rate limit, overflows context, or returns malformed JSON produces
none of `complete`. Use
`python3 "$P/scripts/agent_team.py" transition --repo . --task-id T-001 --status blocked --note "..."`.

## Knobs, limits, gotchas

- **Parallelism**: tasks may run concurrently only with exclusive file ownership or read-only
  scope. `promote` is coordinator-serialized and refuses to run from a linked worktree.
- **Lanes and model**: adapters declare 20 logical lanes and the `auto` model; lanes are durable
  identities, and backend throttling changes retry eligibility (`core/lanes.py`), never the lane
  count.
- **Commands run without a shell.** `cmd` is split with `shlex`; `&&`, pipes, redirects, and
  substitutions are rejected as divergences rather than guessed at. Wrap compound commands in a
  script and record the script.
- **Command timeout**: `verify --timeout` (default 600s) per command.
- **Evidence boundary**: never infer completion from a chat message, idle event, timeout recovery,
  or a worker's own summary. The verifier's executable result is the veto.
- **Cost**: the scaffold spends roughly 3x the tokens of a single call; it is worth it when the
  single call is bottlenecked on organisation, context, or token caps, and harmful when the model
  already had the right plan (anchoring). Keep a single-call baseline per task class.
- **Python**: 3.9+ for the original core; the new runtime is stdlib-only.

## Evidence

- `python -m pytest tests/ -q` → 15 passed (core protocol, lanes, publish/verify/promote, veto,
  immutability, hook boundary).
- End-to-end demo on a scratch repository: task assigned → worker worktree committed → `publish`
  → `verify` `accept` → `promote` staged `app.py`/`test_app.py` and closed `T-001`; a second
  attempt with a failing command was `reject`ed and `promote` exited `2` without touching the main
  checkout; `reconcile` reported both attempts; `install --with-hooks` landed the skill, subagents,
  command and guard, and the guard blocked a worker write into the main checkout.
