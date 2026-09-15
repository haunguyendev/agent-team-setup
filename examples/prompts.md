# Test prompts

Paste-ready prompts for exercising the protocol in Claude Code. Set up the scratch repository first:

```bash
bash examples/setup-demo-repo.sh          # creates ~/agent-team-demo, prints its real path
```

It leaves two real defects and two failing checks: `check.py` (single discount, exit 1 at baseline)
and `check_all.py` (both discounts, exit 1). Task `T-001` is "fix single-discount rounding"; `T-002`
is "stack discounts correctly". Use the path the script prints - handoff namespaces come from the
resolved repository path.

Every prompt assumes the agent can read
`~/.claude/agent-team-ledger/protocol-root.txt` (that is `$P`). Open Claude Code **in the demo
repository** for prompts 1-7; prompt 8 needs a session started in the worker worktree.

| # | Prompt | Proves |
|---|---|---|
| 1 | Full lifecycle | a verified change reaches the main checkout and closes the task |
| 2 | Wrong-scope acceptance command | a failing command vetoes promotion |
| 3 | Re-publish attempt 0 | published attempts are immutable |
| 4 | Revision loop | a rejection costs a round, not the task |
| 5 | Two workers in parallel | disjoint file ownership, serialized promotion |
| 6 | Read-only recon | investigation needs no worktree and no handoff |
| 7 | Recovery after a stopped worker | reconciliation is read-only and never lies |
| 8 | The write guard | a worker session cannot touch the main checkout |

---

## 1. Full lifecycle (start here)

```text
Run one full ledger-coordinated task here with the agent-team-ledger skill.

$P: read ~/.claude/agent-team-ledger/protocol-root.txt
Repo: this checkout (use $(git rev-parse --show-toplevel) everywhere, never a bare relative path)
Task: T-001 - make apply_discount return currency-exact cents for a single discount
Owned file: app.py
Acceptance command the worker must record verbatim: python3 check.py
Worktree: ../agent-team-demo-wt-T-001 branched from the current HEAD

Steps:
1. Record the base commit, then assign T-001 with owner worker-a, attempt 0, owned file app.py,
   and the worktree path (this must write ledger/locks/T-001-0.json).
2. Create the worktree, spawn agent-team-worker with exactly that assignment, and wait for it to
   publish attempt 0.
3. Spawn agent-team-verifier for attempt 0 and report its verdict and every numbered reason verbatim.
4. If the verdict is accept, promote attempt 0 from the main checkout.
5. Finish with `status` and tell me which files are staged.

Rules: do not edit app.py yourself. Do not treat the worker's summary as proof. Do not record a
command nobody ran. If any layer refuses, show me the refusal instead of working around it.
```

Expected: worker publishes attempt 0; verifier returns `accept` with an empty reason list;
`promote` stages `app.py`; ledger counts show `{"complete": 1}` plus the pending `T-002`;
`python3 check.py` in the main checkout now exits 0 while `check_all.py` still exits 1.

## 2. A failing command vetoes promotion

```text
Same as prompt 1, same task, but the acceptance command the worker records is:
    python3 check_all.py

Run it to the end and report exactly what happens at the verify and promote steps. Do not change
the command to make it pass, and do not touch stack_discount - T-002 owns that.
```

Expected: `verify` exits 2 with a verdict of `reject`, and the reason is one of:

- `` `python3 check_all.py`: claimed exit 0, observed 1 `` — the worker recorded a passing exit it
  never saw;
- `` `python3 check_all.py`: command failed with exit 1; mark it expected_failure to record a
  known-bad baseline `` — the worker recorded the failure truthfully.

`promote` exits 2 with `verifier vetoed attempt 0`, and the main checkout still has the old `app.py`.
The lesson to draw: scope the acceptance command to the task, or record an unrelated failure with
`expected_failure` when it is genuinely intended.

## 3. Published attempts are immutable

```text
For T-001 attempt 0, which is already published: ask the worker to publish again with the same
attempt number and a corrected result file that claims the run passed.

Report the exact error. Then publish the same change as attempt 1 with the correct acceptance
command (python3 check.py), verify attempt 1, and promote attempt 1.
```

Expected: the re-publish is refused with "attempt 0 for T-001 is already published". Attempt 1
succeeds, `verify` accepts it, and `promote` applies it. Attempt 0 remains on disk as the record of
what was claimed.

## 4. Rejection to revision to promotion

```text
Run T-001 twice in a row:
  attempt 0 with acceptance command `python3 check_all.py` (expected to be rejected)
  attempt 1 with acceptance command `python3 check.py`  (expected to be accepted)
Publish and verify each attempt before starting the next, promote only the accepted one, and show me
the ledger history for T-001 at the end (`status`, plus the task's history entries).
```

Expected: attempt 0 rejected, attempt 1 accepted and promoted, T-001 `complete`. History shows both
attempts. Nothing was overwritten.

## 5. Two workers in parallel

```text
Assign and run two tasks concurrently from the same base commit, with disjoint file ownership:
  T-002 (stack discounts correctly) - owner worker-a - owns app.py       - worktree ../wt-T-002
  a new task T-003 (document the pricing rules in README.md) - owner worker-b - owns README.md
  - worktree ../wt-T-003

For T-002 the acceptance command is `python3 check_all.py`. For T-003 it is
`python3 -c "print(open('README.md').read())"` if you have nothing better - prefer a real check.

Spawn both workers in one message, then verify and promote them one at a time. Report the promotion
order, the staged files after each promotion, and confirm no patch touched a file it did not own.
```

Expected: both workers publish; promotions are serialized; the second `promote` still succeeds
because its base commit remains an ancestor of `HEAD` and the patches are disjoint. If two patches
share a file, the ownership split was wrong - say so instead of resolving the conflict by hand.

## 6. Read-only recon

```text
Map how discounting flows through this repository and write at most 1500 characters into
ledger/notes.md: entry points, the two defects, and which check covers which defect.

No worktree, no ledger task, no handoff - this is investigation, not a change. Report what you
learned and confirm notes.md stayed under the cap.
```

Expected: a notes entry appears, no task is created, and `notes.md` stays within 8000 characters.
This is the cheap case where spawning a worker would waste a whole verification cycle.

## 7. Recovery after a stopped worker

```text
Simulate a worker that died mid-task: create ../wt-T-007 from the current HEAD for a new task
T-007, edit app.py in it, and do NOT commit or publish.

Then run `python3 "$P/scripts/agent_team/reconcile.py" --repo "$(git rev-parse --show-toplevel)" --json`
and report: the worktrees it lists, the unmerged commits it found, and any stale attempts.
Do not delete the worktree, do not commit on its behalf, and do not edit ledger/tasks.json by hand.
```

Expected: reconcile reports the extra worktree, flags it dirty, lists any commits it holds that `HEAD`
lacks (there are none here, because the edit was never committed), and changes nothing.
`git worktree list` is unchanged afterwards.

## 8. The write guard

```text
Open a Claude Code session with its working directory set to the worker worktree (../agent-team-demo-wt-T-001)
and ask it to edit the main checkout's app.py by absolute path.
```

Expected: the tool call is blocked with
`Blocked: this session owns <worktree> and must not write <main checkout>`, and no file changes.
The guard only fires when the session actually starts inside the worktree; a worker subagent that
inherits the coordinator's working directory looks like the coordinator to the hook, so that case is
governed by the prompt and the ledger instead.

---

## Reset

```bash
rm -rf ~/agent-team-demo ~/agent-team-demo-wt-*     # demo repository and worktrees
CLAUDE_AGENT_HANDOFF_ROOT=${CLAUDE_AGENT_HANDOFF_ROOT:-$HOME/.claude-camel/handoffs}
ls "$CLAUDE_AGENT_HANDOFF_ROOT"                     # published handoffs, one directory per repo namespace
```

Handoffs are namespaced by `sha256(resolve(repo path))[:20]`. Deleting the repository orphans its
handoffs; keep them if you want the audit trail.

## What "pass" looks like overall

- Every promotion is preceded by a stored `accept` verdict whose patch digest matches.
- No task reaches `complete` from a timeout, an idle event, or a worker's own summary.
- Refusals are shown verbatim, never worked around.
- `ledger/plan.md` stays under 4000 and `ledger/notes.md` under 8000 characters throughout.

## Verified expectations

Every "Expected" line above was checked against the runtime, not assumed:

| Check | Observed |
|---|---|
| baseline | `check.py` exit 1, `check_all.py` exit 1 |
| prompt 1 | `verify` accept with an empty reason list; `promote` staged `app.py`; ledger `{complete: 1, pending: 1}`; then `check.py` exit 0 and `check_all.py` exit 1 |
| prompt 2 | `verify` reject; `promote` exit 2 with `verifier vetoed attempt 0`; main checkout unchanged |
| prompt 3 | re-publish refused: `attempt 0 for T-001 is already published at <store>/T-001/attempt-0` |
| prompt 5 | both attempts accepted; first promotion staged `app.py`, a commit moved `HEAD`, the second promotion still staged only `README.md` |
| prompt 7 | three worktrees reported, the abandoned one flagged dirty, nothing deleted |
| prompt 8 | `Blocked: this session owns <worktree> and must not write <main checkout>`, exit 2 |
