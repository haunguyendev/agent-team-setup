# Coordination protocol

## Ownership

The coordinator owns task state, `tasks.json`, `PROGRESS.md`, promotion records, and merges.
Each worker owns only its isolated worktree and its current attempt. A worker never writes
another checkout, even when an absolute path is available in the environment.

## GVS5H adaptations

Use a short plan, a small live queue, bounded notes, and fresh contexts. Re-curate the queue
after every result. Persist complete evidence externally and place only summaries and pointers
in the compact state. A verifier’s executable result vetoes a confident model report.

The paper’s single shared workspace becomes two layers here: private worktrees for source
changes, and a durable external handoff store for artifacts. This prevents Claude Code’s
worktree safety boundary from being violated.

## Lifecycle

`pending → assigned → working → review → approved → complete`

Failure states are explicit: `revision_required`, `blocked`, `unmeasured`, and `rejected`.
Stopping, timeout, rate limiting, context overflow, or malformed output never implies success.
Retries append an attempt; they do not overwrite history.

## Parallelism

All configured streams may run. Parallel work is safe only when tasks have exclusive file
ownership or are read-only. Promotion and merge are coordinator-serialized. A task lock must
identify repository, task, attempt, owner, files, and base commit.

## Recovery

Before cleanup, record worktree path, branch, base/current commit, dirty files, handoff status,
and review disposition. Reconciliation is read-only. Missing markers, bad hashes, malformed
JSON, stale attempts, and unmerged commits remain recoverable and visible.
