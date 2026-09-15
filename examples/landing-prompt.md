# Landing page test prompt

A light, fast end-to-end test of the agent team: build a static landing page for a pet-food shop,
with an objective acceptance script instead of an opinion.

## Setup (once)

```bash
bash examples/setup-landing-demo.sh          # creates <protocol root>/landing-demo
```

The script creates the project, commits it, bootstraps the ledger with `T-001`, and prints the
baseline check, which fails with 11 concrete failures:

```
FAIL (11)
  1. <meta name="viewport"> is required
  ...
 11. the order form needs a submit <button>
```

`README.md` in the project is the brief (brand, three products with fixed prices, required section
ids, order form, alt text, no framework). `check.py` is the acceptance script: `exit 0` only when
the brief is met. It exists so the verifier has something executable to rerun.

## The prompt

Open Claude Code **in the demo project** (`landing-demo/`) and paste:

```text
Build the Bát Cơm landing page with the agent-team-ledger protocol.

$P: read ~/.claude/agent-team-ledger/protocol-root.txt
Repo: this checkout (always use $(git rev-parse --show-toplevel), never a bare relative path)
Brief: README.md - it is the spec, follow it exactly
Task: T-001 (already in the ledger, status pending) - build the landing page so the acceptance check passes
Owned files: index.html, styles.css - touch nothing else
Acceptance command the worker must record verbatim: python3 check.py
Worktree: ../landing-demo-wt-T-001 branched from the current HEAD

Keep it light and fast: two files, plain HTML + CSS, no framework, no build step, no external JS.
Remove the dead <script src="app.js"> reference while you are in there.

Do this, in order:
1. Read ledger/tasks.json and README.md, record the base commit, then assign T-001 to worker-a,
   attempt 0, owned files index.html and styles.css, with the worktree path above.
2. Create the worktree and spawn agent-team-worker with that assignment plus the brief. Wait for it
   to publish attempt 0.
3. Spawn agent-team-verifier for attempt 0 and report its verdict and every numbered reason verbatim.
4. If the verdict is accept, promote attempt 0 from the main checkout, then re-run
   `python3 check.py` in the main checkout and show me the output.
5. Finish with `status` and the list of staged files.

Rules: do not write index.html or styles.css yourself - the worker owns them. Do not treat the
worker's summary as proof; the verifier's re-run is the proof. Do not edit ledger/tasks.json by
hand. If a layer refuses, show me the refusal instead of working around it.
```

## The same prompt on OMP

OMP reads this package's skill and slash command from `~/.claude` through its `claude` discovery
provider, and `install.sh --target both` also writes native copies under `~/.omp/agent` (agents,
skill, command, and the `hooks/pre/handoff_guard.ts` guard). Agents, hooks and skills are discovered
at session start, so open a fresh session in the demo repository:

```bash
cd landing-demo && omp
```

```text
/agent-team build the Bát Cơm landing page - README.md is the spec, keep going until python3 check.py exits 0
```

The coordinator dispatches with the `task` tool - `{ agent: "agent-team-worker", task: "<assignment>" }`,
one item per worker, several items in one `tasks[]` batch for parallel work. Everything else is the
same as above, including the acceptance command and the promotion gate.

## What to expect

| Step | Expected |
|---|---|
| assign | `ledger/locks/T-001-0.json` created |
| worker | worktree committed, attempt 0 published with a patch touching `index.html` and `styles.css` |
| verify | `accept`, empty reason list, `python3 check.py` observed at exit 0 |
| promote | staged `index.html` and `styles.css`; task `T-001` complete |
| final check | `PASS - landing page meets the brief` in the main checkout |

Then look at it:

```bash
open landing-demo/index.html
```

## Variants worth running afterwards

- **Rejection:** paste the same prompt but record `python3 check.py --strict` (a flag that does not
  exist) so the rerun fails with exit 2 and the verifier vetoes; the main checkout keeps the
  placeholder page. Shows why the acceptance command must be one the worker actually ran.
- **Parallel:** add a second task for `README.md` (document the page) and run both workers at once -
  disjoint files, promotions serialized.
- **Recovery:** stop the worker mid-attempt, then run
  `python3 "$P/scripts/agent_team/reconcile.py" --repo . --json` and confirm it reports the dirty
  worktree without deleting anything.

## Notes

- `check.py` is deliberately strict but achievable: a reference implementation passes it. If the
  worker cannot get it green twice in a row, the brief is ambiguous - fix the brief, not the check.
- The demo is excluded from this repository's history (`/landing-demo/` in `.gitignore`), because it
  is its own git repository.
