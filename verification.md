# Verification matrix

| Layer | Required proof |
|---|---|
| Worker | Valid result JSON, immutable handoff marker, manifest hashes, base commit |
| Core | Result provenance, atomic JSON writes, request-id/payload binding, 20-lane boundary |
| Critic | Independent scope/evidence verdict with numbered reasons |
| Verifier | Exact commands rerun with exit codes and divergences; a failing command vetoes unless recorded as `expected_failure` |
| Coordinator | Promotion record, task-state transition, merge disposition |
| Recovery | Worktree/branch/dirty-state record before cleanup |
| Project | Existing project safety and build/deploy gates remain enforced |

No layer may infer completion from a chat message, idle event, timeout recovery, or a worker’s
self-reported success.

The canonical core is tested independently from project adapters. A project is ready only when
its adapter inspection, local compatibility scripts, hooks, and the shared core tests all pass.
