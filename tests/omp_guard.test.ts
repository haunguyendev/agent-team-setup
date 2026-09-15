/**
 * Guard rule tests. Run with: bun run tests/omp_guard.test.ts
 *
 * The git runner is faked, so these assert the decision rule, not git itself.
 */
import { decide } from "../integrations/omp/hooks/pre/handoff_guard.ts";

const MAIN = "/repo";
const WORKTREE = "/wt-T-001";
const SIBLING = "/wt-T-002";

function fakeRun(files: Record<string, string>) {
  return (cwd: string, args: string[]): string | null => {
    const key = `${cwd} ${args.join(" ")}`;
    return files[key] ?? null;
  };
}

const topology: Record<string, string> = {
  [`${WORKTREE} rev-parse --show-toplevel`]: WORKTREE,
  [`${MAIN} rev-parse --show-toplevel`]: MAIN,
  [`${MAIN} rev-parse --path-format=absolute --git-common-dir`]: `${MAIN}/.git`,
  [`${WORKTREE} rev-parse --path-format=absolute --git-common-dir`]: `${MAIN}/.git`,
  [`${SIBLING} rev-parse --path-format=absolute --git-common-dir`]: `${MAIN}/.git`,
  [`${SIBLING} rev-parse --show-toplevel`]: SIBLING,
};

const failures: string[] = [];
let checks = 0;

function expect(label: string, actual: unknown, wanted: unknown) {
  checks += 1;
  const a = JSON.stringify(actual);
  const w = JSON.stringify(wanted);
  if (a !== w) failures.push(`${label}\n    expected ${w}\n    got      ${a}`);
}

// A worker session inside its worktree must not touch the main checkout.
expect(
  "worker -> main checkout is blocked",
  decide(
    { cwd: WORKTREE, toolName: "write", input: { path: `${MAIN}/app.py` } },
    fakeRun(topology),
  )?.block,
  true,
);

// Nor a sibling worktree of the same repository.
expect(
  "worker -> sibling worktree is blocked",
  decide(
    { cwd: WORKTREE, toolName: "edit", input: { path: `${SIBLING}/app.py` } },
    fakeRun(topology),
  )?.block,
  true,
);

// Its own worktree is its business (the main checkout's `.git` is a directory, the worktree's is a file).
expect(
  "worker -> own worktree is allowed",
  decide({ cwd: WORKTREE, toolName: "write", input: { path: `${WORKTREE}/app.py` } }, fakeRun(topology)),
  undefined,
);

// Relative paths resolve against the session cwd.
expect(
  "relative path inside the worktree is allowed",
  decide({ cwd: WORKTREE, toolName: "edit", input: { path: "src/app.py" } }, fakeRun(topology)),
  undefined,
);

// A read is not a write.
expect(
  "read tool is ignored",
  decide({ cwd: WORKTREE, toolName: "read", input: { path: `${MAIN}/app.py` } }, fakeRun(topology)),
  undefined,
);

// A writer without a path field is not the guard's business.
expect(
  "write tool without a path is ignored",
  decide({ cwd: WORKTREE, toolName: "write", input: {} }, fakeRun(topology)),
  undefined,
);

// Outside any repository nothing is claimed.
expect(
  "not a repository is ignored",
  decide({ cwd: "/tmp", toolName: "write", input: { path: "/tmp/x" } }, fakeRun(topology)),
  undefined,
);

// A different repository is a different concern.
const foreign: Record<string, string> = {
  ...topology,
  ["/tmp rev-parse --show-toplevel"]: "/tmp",
  ["/tmp rev-parse --path-format=absolute --git-common-dir"]: "/tmp/.git",
};
expect(
  "another repository is ignored",
  decide({ cwd: WORKTREE, toolName: "write", input: { path: "/tmp/x.py" } }, fakeRun(foreign)),
  undefined,
);

if (failures.length > 0) {
  console.error(`FAIL (${failures.length}/${checks})`);
  for (const failure of failures) console.error(`  - ${failure}`);
  process.exit(1);
}
console.log(`PASS - ${checks} guard rules hold`);
