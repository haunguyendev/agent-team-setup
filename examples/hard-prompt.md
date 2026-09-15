# Hard task prompt: order engine with a frozen contract

A harder demo than the landing page: three modules, real invariants, money rounding, idempotency, and
a dependency that forces the coordinator to sequence work. Use it when you want to see the ledger team
actually coordinate - parallel workers, disjoint ownership, a verifier that reruns the work, and a
promotion gate.

## Setup (once)

```bash
bash examples/setup-hard-demo.sh          # creates <protocol root>/hard-demo
```

The project ships a frozen contract in `README.md`, three defective stubs (`pricing.py`,
`inventory.py`, `orders.py`), an objective acceptance harness `check.py`, a git repository and a
three-task ledger. The baseline fails in every section:

```
FAIL (3)
  1. pricing: crashed - NotImplementedError: pricing.subtotal
  2. inventory: crashed - NotImplementedError: Inventory.__init__
  3. orders: crashed - NotImplementedError: Inventory.__init__
```

`check.py` is runnable per section - `python3 check.py pricing` - which is what lets each worker own
one module. `examples/hard-demo/reference-solution/` holds a solution that passes the harness; it is
**not** copied into the demo project and exists so the task stays provably achievable
(`tests/test_hard_demo.py` asserts both facts).

## The prompt

```text
Build the Bát Cơm order engine in this repository, following README.md.

The ledger already has three tasks: T-001 (pricing.py), T-002 (inventory.py), T-003 (orders.py).
Run T-001 and T-002 in parallel - their files are disjoint and they share no state. Promote both
before you start T-003, because orders.py imports the other two modules; assign T-003 from the base
commit that exists after those promotions.

For each task: assign it with exclusive file ownership, create the worktree, dispatch
agent-team-worker with the absolute worktree path, the base commit, the owned file, the acceptance
command from README.md, and the brief. Then dispatch agent-team-verifier for the attempt and report
its verdict with the numbered reasons verbatim.

Publish discipline: the worker publishes each attempt with the true exit code, even when the
acceptance command is still red. A red attempt with honest evidence is a valid outcome - the
verifier's veto is what sends it back. Do not hold work back to look good, and never record a command
nobody ran.

Finish by running python3 check.py (all sections) in the main checkout and showing me the output.
Report ledger facts only: task id, attempt, verdict, staged files.
```

## What to expect

| Step | Expected |
| --- | --- |
| T-001, T-002 | two workers in parallel, disjoint files, two published attempts |
| verify | reruns `check.py pricing` / `check.py inventory` against the recorded commit |
| first attempts | often red - see below; a `reject` costs one attempt, not the task |
| promotion | serialized: both promoted from a clean main checkout, task state `complete` |
| T-003 | assigned only after both promotions, from the new `HEAD` |
| final | `PASS - all meets the brief` in the main checkout |

## What usually fails first (and why it is the point)

- **Half-up rounding.** `round()` is banker's rounding: `25.000,5` becomes `25.000`, the brief wants
  `25.001`. A worker using floats and `round()` fails `check.py pricing` on two assertions.
- **Operation order.** Applying the coupon before the tier discount changes the result; the brief
  fixes subtotal → tier → coupon → shipping.
- **Idempotency.** A second `create("O1", ...)` must not reserve twice, and a second `release` must be
  a no-op. Check-then-act implementations fail four assertions.
- **Defensive copies.** `reserved()` must hand out a copy; returning the internal dict fails.
- **Dependency order.** Assigning T-003 in parallel with T-001/T-002 produces a worker whose worktree
  still holds the stubs, so its acceptance command cannot pass. That is the coordinator's error, not
  the worker's.

On concurrency, read the brief's note: `check.py` asserts no double spend in a 16-thread burst, which
is sound but incomplete on CPython. Do not present that assertion as proof of lock-freedom.

## Variants

- **Serial baseline:** run only T-001 first, promote, then T-002, then T-003. Compare attempts,
  wall-clock, and token spend against the parallel plan.
- **Veto demo:** tell the worker for T-001 to record `python3 check.py` (all sections) as its
  acceptance command while only `pricing.py` is implemented; the verifier rejects it because
  `orders`/`inventory` still crash. The main checkout stays untouched.
- **Anchoring demo:** after a rejection, spawn a fresh worker that does **not** read `ledger/notes.md`
  and compare its approach with the revision worker's.

## Notes

- The acceptance harness is read-only for workers; a verifier should reject an attempt whose patch
  touches `check.py`. Ask for that check explicitly if you want it enforced on this run.
- The demo project is excluded from this repository's history (`/hard-demo/` in `.gitignore`).
