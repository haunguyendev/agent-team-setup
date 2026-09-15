/**
 * Write-boundary guard: a worker never writes another checkout.
 *
 * OMP discovers hook factories at <config>/hooks/pre/*.{ts,js}, so this file must stay in a `pre/`
 * directory. The rule mirrors the Claude Code guard: a session whose cwd is a linked git worktree
 * may only write inside that worktree, never the coordinator's main checkout or a sibling worktree.
 */
import { execFileSync } from "node:child_process";
import { existsSync, statSync } from "node:fs";
import { dirname, isAbsolute, resolve } from "node:path";

import type { HookAPI } from "@oh-my-pi/pi-coding-agent/extensibility/hooks";

const WRITE_TOOLS: Record<string, true> = {
  write: true,
  edit: true,
  multiedit: true,
  ast_edit: true,
  "ast-grep": true,
  notebook: true,
};

const PATH_KEYS = ["path", "file_path", "filePath", "notebook_path", "target"];

export type Decision = { block: true; reason: string } | undefined;
export type Runner = (cwd: string, args: string[]) => string | null;

/** Test seam: the git runner is injectable so the rule can be exercised without spawning git. */
export function gitRun(cwd: string, args: string[]): string | null {
  try {
    return execFileSync("git", ["-C", cwd, ...args], {
      encoding: "utf8",
      stdio: ["ignore", "pipe", "ignore"],
    }).trim();
  } catch {
    return null;
  }
}

export function decide(
  event: { cwd: string; toolName: string; input: Record<string, unknown> },
  run: Runner = gitRun,
): Decision {
  if (!WRITE_TOOLS[event.toolName]) return undefined;

  let raw: string | null = null;
  for (const key of PATH_KEYS) {
    const value = (event.input ?? {})[key];
    if (typeof value === "string" && value.trim()) {
      raw = value;
      break;
    }
  }
  if (!raw) return undefined;

  const sessionTop = run(event.cwd, ["rev-parse", "--show-toplevel"]);
  if (!sessionTop) return undefined;
  const gitPointer = resolve(sessionTop, ".git");
  if (existsSync(gitPointer) && statSync(gitPointer).isDirectory()) return undefined; // coordinator checkout

  const target = isAbsolute(raw) ? raw : resolve(event.cwd, raw);
  const targetTop = run(dirname(target), ["rev-parse", "--show-toplevel"]);
  if (!targetTop || targetTop === sessionTop) return undefined;

  const sessionCommon = run(event.cwd, ["rev-parse", "--path-format=absolute", "--git-common-dir"]);
  const targetCommon = run(dirname(target), ["rev-parse", "--path-format=absolute", "--git-common-dir"]);
  if (!sessionCommon || sessionCommon !== targetCommon) return undefined;

  return {
    block: true,
    reason:
      `Blocked: this session owns ${sessionTop} and must not write ${targetTop}. ` +
      "Publish an immutable handoff instead; only the coordinator promotes changes.",
  };
}

export default function hook(pi: HookAPI): void {
  pi.on("tool_call", async (event, ctx) => {
    return decide({
      cwd: ctx?.cwd ?? process.cwd(),
      toolName: event.toolName,
      input: (event.input ?? {}) as Record<string, unknown>,
    });
  });
}
