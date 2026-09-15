# Operations runbook: spawning agent teams on real code

For running actual work in a real repository: when to spawn, what to put in the spawn prompt, how
to keep parallel workers from colliding, and what to do when a layer refuses.

Commands are verified locally (see [Evidence](#14-evidence-and-what-is-not-verified)). Treat the CI
section as a template to adapt, not as a tested pipeline.

## 1. Where to install

Machine setup, once:

```bash
gh repo clone <owner>/agent-team-setup ~/.local/share/agent-team-setup
P=~/.local/share/agent-team-setup
bash "$P/install.sh"                    # global: ~/.claude, hook included
bash "$P/install.sh" --project "$PWD"   # or one project only, into $PWD/.claude
bash "$P/install.sh" --check            # verify an existing install
```

The script is additive and idempotent: existing agent assets are kept, `settings.json` is backed up
before the guard is merged, and a second run does not duplicate the hook. `--global-dir` (or
`AGENT_TEAM_HOME`) chooses where the package is cloned to when the script runs standalone, e.g. piped
from a raw URL on a public fork.

| Scope | Lands in | Hook command | Use when |
|---|---|---|---|
| global (`--scope user`, default in `install.sh`) | `~/.claude/` | `python3 /abs/path/.claude/hooks/handoff_guard.py` | you want every project guarded |
| project (`--project DIR`) | `<repo>/.claude/` | `python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/handoff_guard.py"` | repo is shared with teammates |

Resolve the protocol root at runtime with `$AGENT_TEAM_ROOT` or read
`.claude/agent-team-ledger/protocol-root.txt`.

The guard's rule is "a session inside a linked worktree may only write inside that worktree". It keys
off the session `cwd`, so it protects you when a worker genuinely runs in its own worktree (its own
terminal, or a session started with `cwd` set there). A worker subagent that shares the coordinator's
`cwd` looks like the coordinator to the hook and cannot be distinguished - for that case the boundary
is the prompt and the ledger, not the hook.

## 2. When to spawn (and when not to)

| Situation | Move | Why |
|---|---|---|
| Fix one file, clear cause | Do it yourself, single context | Spawn overhead and ~3x token cost exceed the benefit |
| Feature across 2+ files, one owner | 1 worker + verifier | Fresh context for the work, external proof for the claim |
| N independent modules/languages | N workers in parallel | Only if file ownership is exclusive |
| Unknown codebase, need a map | Read-only explorer spawns | Produces notes, not patches - no handoff needed |
| Needs a product/architecture decision | Coordinator asks the human, task goes `blocked` | No agent may invent the answer |

Rule of thumb: spawn when the single context is the bottleneck - long transcript, token cap,
several layers of reasoning (design, then implement, then prove). Do not spawn to look busy.

## 3. Spawn mechanics

The coordinator session is the scheduler. A spawned worker gets a **blank context**: whatever you do
not put in the prompt does not exist for it. Spawn with the agent definition, so the role prompt
(and the write boundary) applies:

```text
Task tool -> subagent_type: "agent-team-worker"   (or agent-team-coordinator / agent-team-verifier)
```

Parallel workers: issue the Task calls in one message. Cross-worker contracts (interfaces, file
ownership, base commit) must be decided **before** spawning, and each worker must be told exactly
which files it owns.

### Worker spawn prompt (template)

```text
Protocol root ($P): /path/to/agent-team-setup
Main repo:          /path/to/repo
Task:               T-001 - <one line>
Attempt:            0
Worktree:           /path/to/repo-../wt-T-001   (create: git -C MAIN worktree add ../wt-T-001 -b agent/T-001 <BASE>)
Base commit:        <BASE>
You own exactly:    app.py, tests/test_app.py   (touch nothing else)
Do not touch:       ledger/, other worktrees, the main checkout
Acceptance:         record this command verbatim, run it yourself first: <cmd>
Result file:        /tmp/T-001-result.json   (schema: schemas/result.schema.json)
Stop condition:     publish succeeds, or publish is refused - report the refusal, do not retry with the same attempt
Report back:        task id, attempt, outcome, files, commands with real exit codes, uncertainty
```

### Verifier spawn prompt (template)

```text
Protocol root ($P): /path/to/agent-team-setup
Main repo:          /path/to/repo
Task:               T-001 attempt 0
Do: run `python3 $P/scripts/agent_team/handoff.py verify --repo MAIN --task-id T-001 --attempt 0 --json`
Report: the verdict, every numbered reason verbatim, and whether the recorded commands actually
exercise the changed files. Do not edit source or the ledger. Do not waive a veto.
```

Coordinator-owned facts a worker must never choose for itself: task id, attempt number, base commit,
owned files, worktree path. If a worker asks for those, the assignment was underspecified.

**Fresh context per attempt.** Never resume a worker's context to "fix" a rejection - open attempt
`N+1` with a fresh worker. When the rejection was conceptual (wrong approach, not a typo), spawn a
fresh-perspective worker that does **not** read `notes.md`: that is the counter to anchoring.

## 4. Recipe A - one task, one worker (default)

```bash
P=~/agent-team-setup; MAIN=$(pwd); BASE=$(git rev-parse HEAD)

python3 "$P/scripts/agent_team.py" add-task --repo "$MAIN" --title "flip the retry policy"
python3 "$P/scripts/agent_team.py" assign --repo "$MAIN" --task-id T-001 --owner worker-a \
  --attempt 0 --files app.py --base-commit "$BASE" --worktree ../wt-T-001
git -C "$MAIN" worktree add ../wt-T-001 -b agent/T-001 "$BASE"
# -> spawn agent-team-worker with the prompt from section 3

python3 "$P/scripts/agent_team/handoff.py" verify  --repo "$MAIN" --task-id T-001 --attempt 0 --json
python3 "$P/scripts/agent_team/handoff.py" promote --repo "$MAIN" --task-id T-001 --attempt 0 --json
```

`promote` stages the change; it does not commit. Your own build/deploy gates still run, then you
commit under your normal message and review conventions.

## 5. Recipe B - parallel workers

Assign every task from the **same** base commit, with disjoint file sets:

| Task | Owner | Owns | Worktree |
|---|---|---|---|
| T-001 | worker-a | `api/routes.py` | `../wt-T-001` |
| T-002 | worker-b | `web/form.tsx` | `../wt-T-002` |
| T-003 | worker-c | `docs/*` | `../wt-T-003` |

Spawn all three in one message, then verify and promote **serially** (promotion is
coordinator-serialized). If two patches touch the same file, the ownership split was wrong - stop
and re-assign instead of resolving the conflict by hand.

Read-only tasks (recon, audits) need no worktree, no handoff, and no ledger task: spawn an explorer
and have it write a bounded summary into `ledger/notes.md`.

## 6. Recipe C - rejection and revision

```bash
# attempt 0 rejected: fix in place, commit again in the worktree, then publish attempt 1
python3 "$P/scripts/agent_team/handoff.py" publish --repo "$MAIN" --worktree ../wt-T-001 \
  --task-id T-001 --attempt 1 --result /tmp/T-001-b.json --base-commit "$BASE" --json
python3 "$P/scripts/agent_team/handoff.py" verify --repo "$MAIN" --task-id T-001 --attempt 1 --json
```

Attempt 0 stays on disk untouched - it is the audit trail of what failed. `verify` refuses to
overwrite an existing verdict, which is why the attempt number must move. Two rounds with no new
evidence means the task is mis-specified: `transition --status blocked` and escalate.

## 7. Recipe D - human gate

```bash
python3 "$P/scripts/agent_team.py" transition --repo "$MAIN" --task-id T-001 \
  --status blocked --note "needs a decision: JSON column vs side table"
python3 "$P/scripts/agent_team.py" status --repo "$MAIN"   # the queue and attention lists
```

After the decision, `assign` again with an incremented attempt. Legal transitions are enforced:
you cannot jump from `assigned` to `complete`, and `complete` is terminal.

## 8. CI wiring (template)

Three jobs: publish on a branch, verify from the artifact, promote on `main` behind approval.

```yaml
name: agent-team
on: workflow_dispatch
jobs:
  worker:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      - uses: actions/checkout@v4
        with: { repository: <owner>/agent-team-setup, path: .protocol }
      - run: |
          python3 .protocol/scripts/agent_team/handoff.py publish \
            --repo . --worktree . --task-id "$TASK" --attempt "$ATTEMPT" \
            --result "$RESULT" --base-commit "$BASE"
      - uses: actions/upload-artifact@v4
        with: { name: handoffs, path: ~/.claude-camel/handoffs }

  verify:
    needs: worker
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      - uses: actions/checkout@v4
        with: { repository: <owner>/agent-team-setup, path: .protocol }
      - uses: actions/download-artifact@v4
        with: { name: handoffs, path: ~/.claude-camel/handoffs }
      - run: |
          python3 .protocol/scripts/agent_team/handoff.py verify \
            --repo . --task-id "$TASK" --attempt "$ATTEMPT" --json   # exit 2 fails the job
```

Notes for real use: the worker checkout is a single checkout, so publish will refuse it as "not an
isolated worktree" - in CI, create a linked worktree first (`git worktree add`) or run the worker in
its own job that checks out the branch into a separate directory. The handoff root must be shared
between jobs (artifact/cache) or every verification fails as unverifiable.

## 9. Cadence

After every result, before assigning anything new:

1. Curate the queue: merge duplicates, close what is finished, add what the result revealed.
2. Keep `plan.md` ≤ 4000 and `notes.md` ≤ 8000 characters. When a cap is hit, curate - do not raise it.
3. Append one factual line to `PROGRESS.md` (promotion, veto, block).
4. `python3 "$P/scripts/agent_team.py" status --repo "$MAIN"` - the queue is what workers see.

Track four numbers per week: attempts per completed task, reject rate, verification latency, and
tokens per completed task. Rising attempts with flat output means the plan is wrong, not the workers.

## 10. Failure playbook

| Symptom | Cause | Action |
|---|---|---|
| `publish` refused: "isolated worktree" | ran it from the main checkout | create a linked worktree |
| `publish` refused: "uncommitted changes" | tracked files not committed | commit in the worktree; untracked scratch is allowed |
| `publish` refused: "base commit is unknown / not an ancestor" | stale or wrong base | re-read `BASE` from the task lock, rebase the worktree |
| `publish` refused: "already published" | attempt number reused | bump `--attempt`; never edit a published attempt |
| `verify` rejected: "claimed exit X, observed Y" | worker recorded an unrun command | re-run it yourself, publish a new attempt with the true exit |
| `verify` rejected: "command failed with exit N" | the evidence fails | fix the code; or mark `expected_failure` if a failing baseline is intended |
| `verify` rejected: "needs a shell" | compound command (`&&`, pipe) | put it in a script and record the script |
| `verify` rejected: timeout / executable not found | environment mismatch | fix the command or the CI image, then re-verify |
| `promote` refused: "no verification verdict" | skipped the verifier | run `verify` first |
| `promote` refused: "verifier vetoed" | open rejection | fix and open a new attempt |
| `promote` refused: "uncommitted tracked changes" | coordinator tree dirty | stash/commit; `ledger/` is excluded on purpose |
| `promote` refused: "not the main checkout" | ran inside a linked worktree | run it from the main checkout |
| `reconcile` reports "damaged: marker mismatch" | payload modified after publication | distrust that attempt, re-publish a new one, keep the damaged one for forensics |
| Orphan worktree / unmerged commits | worker stopped, or promotion never happened | `reconcile --json`, decide per worktree, then clean |

Nothing in this protocol auto-deletes: worktrees, branches, and failed attempts survive until a human
or the coordinator decides otherwise.

## 11. Recovery and cleanup

```bash
python3 "$P/scripts/agent_team/reconcile.py" --repo "$MAIN" --json
```

It reports worktrees (path/branch/head/dirty), commits present in a worker but not in `HEAD`, every
handoff with its integrity state, and stale (unverified) attempts. Before removing anything, record:
worktree path, branch, base and current commit, dirty files, handoff status, review disposition. Then
`git worktree remove <path>` and decide branch/handoff retention separately. Keep accepted handoffs as
the audit trail; they live outside the repository, so they survive checkout cleanup.

## 12. Cost and limits

- Expect roughly **3x tokens** versus a single call, and ~15-30% overhead in wall-clock per task from
  worktree and verification steps.
- The scaffold wins when a single context is bottlenecked; it loses when the model already had the
  right approach (its errors then propagate through the ledger - anchoring). Keep a single-call
  baseline for each task class and compare.
- `core/lanes.py` provides durable lane identity and backoff bookkeeping for throttled backends. The
  handoff runtime does not call it yet - attempt bookkeeping currently lives in the ledger. Adapters
  declare 20 logical lanes and the `auto` model.
- Read-only workers can run wide; writers are limited by file ownership, not by a global worker cap.

## 13. Anti-patterns

- Spawning a worker without a base commit, owned file list, or acceptance command.
- Letting a worker choose its own scope, or read the coordinator's transcript.
- Promoting on a worker's summary, a green local run, or "it looks right".
- Reusing an attempt number, editing a published handoff, or deleting a failed attempt to tidy up.
- Parallel workers sharing a file.
- Raising the `plan.md`/`notes.md` caps instead of curating.
- Marking a task `complete` while it is `blocked`, `unmeasured`, or `revision_required`.

## 14. Evidence and what is not verified

- `python -m pytest tests/ -q` -> 22 passed: result validation, atomic ledger writes, publish
  preconditions, immutability and tamper detection, verifier veto (divergence, failing evidence,
  `expected_failure`), promotion preconditions, hook write boundary, installer scope behaviour, and
  `install.sh` (global/project scope, idempotent re-install, check mode, unknown-option failure).
- Standalone install: `install.sh` copied to an empty directory with a fresh `HOME` cloned the
  package into `AGENT_TEAM_HOME`, wired `~/.claude`, and pinned the protocol root - the piped-install
  path, exercised against the private remote.
- End-to-end CLI run on a scratch repository: `init` -> `assign` -> worker worktree commit ->
  `publish` -> `verify accept` -> `promote` (staged files, task `complete`) -> a second attempt with a
  failing command was `reject`ed and `promote` exited 2 with the main checkout untouched ->
  `reconcile` reported both attempts -> `install --with-hooks` registered the guard and the guard
  blocked a worker write into the main checkout.
- **Not verified:** the CI workflow above (template only), GitHub-side branch protection, and
  multi-machine handoff sharing. Verify them in your own pipeline before relying on them.
