"""Install the ledger protocol wiring into a coding agent configuration.

Two harnesses are supported from one source of truth:

* Claude Code reads skills, subagents and commands from ``<project>/.claude`` or ``~/.claude``, and
  takes its write guard from a ``settings.json`` hook.
* OMP reads them from ``<project>/.omp`` or ``~/.omp/agent``, discovers agent definitions from
  ``agents/``, and discovers hook factories by path from ``hooks/pre/*.ts`` - no settings entry.

Installation is additive: existing files are never overwritten unless ``--force`` is passed, and
``settings.json`` is edited only behind ``--with-hooks``, after writing a timestamped backup.
"""
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

from core.protocol import ProtocolError

ROOT = Path(__file__).resolve().parents[2]
INTEGRATIONS = ROOT / "integrations"
HARNESSES = ("claude", "omp")
GUARD_MATCHER = "Write|Edit|MultiEdit|NotebookEdit"
GUARD_COMMAND = 'python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/handoff_guard.py"'

SHARED_ASSETS = (
    ("shared/skills/agent-team-ledger/SKILL.md", "skills/agent-team-ledger/SKILL.md"),
    ("shared/commands/agent-team.md", "commands/agent-team.md"),
)
CLAUDE_ASSETS = (
    ("claude-code/agents/agent-team-coordinator.md", "agents/agent-team-coordinator.md"),
    ("claude-code/agents/agent-team-worker.md", "agents/agent-team-worker.md"),
    ("claude-code/agents/agent-team-verifier.md", "agents/agent-team-verifier.md"),
)
CLAUDE_HOOKS = (("claude-code/hooks/handoff_guard.py", "hooks/handoff_guard.py"),)
OMP_ASSETS = (
    ("omp/agents/agent-team-coordinator.md", "agents/agent-team-coordinator.md"),
    ("omp/agents/agent-team-worker.md", "agents/agent-team-worker.md"),
    ("omp/agents/agent-team-verifier.md", "agents/agent-team-verifier.md"),
)
OMP_HOOKS = (("omp/hooks/pre/handoff_guard.ts", "hooks/pre/handoff_guard.ts"),)
AGENTS_SNIPPET = "shared/AGENTS.snippet.md"


def config_root(harness: str, repo: Path, scope: str) -> Path:
    if scope == "user":
        return (Path.home() / ".claude") if harness == "claude" else (Path.home() / ".omp" / "agent")
    if scope != "project":
        raise ProtocolError("scope must be 'project' or 'user'")
    return (repo / ".claude") if harness == "claude" else (repo / ".omp")


def resolve_targets(requested: str, repo: Path, scope: str) -> list[str]:
    """``auto`` installs Claude Code always, and OMP only where OMP already lives."""
    if requested == "both":
        return list(HARNESSES)
    if requested in HARNESSES:
        return [requested]
    if requested != "auto":
        raise ProtocolError("target must be auto, claude, omp, or both")
    detected = ["claude"]
    probe = Path.home() / ".omp" if scope == "user" else repo / ".omp"
    if probe.exists():
        detected.append("omp")
    return detected


def _copy(source: Path, target: Path, force: bool) -> str:
    if target.exists() and not force:
        return f"kept existing {target}"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return f"wrote {target}"


def _registered_commands(pre_tool_use: list) -> list[str]:
    return [
        hook.get("command")
        for entry in pre_tool_use
        if isinstance(entry, dict)
        for hook in entry.get("hooks", [])
        if isinstance(hook, dict)
    ]


def _merge_hooks(settings: Path, command: str, matcher: str) -> str:
    settings.parent.mkdir(parents=True, exist_ok=True)
    existing: dict = {}
    if settings.exists():
        try:
            existing = json.loads(settings.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise ProtocolError(f"{settings} is not valid JSON: {error}") from error
        shutil.copy2(settings, settings.with_suffix(settings.suffix + f".bak-{int(time.time())}"))
    pre = existing.setdefault("hooks", {}).setdefault("PreToolUse", [])
    if command in _registered_commands(pre):
        return f"hook already registered in {settings}"
    pre.append({"matcher": matcher, "hooks": [{"type": "command", "command": command}]})
    settings.write_text(json.dumps(existing, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return f"registered handoff guard in {settings}"


def install(
    repo: Path,
    scope: str = "project",
    target: str = "auto",
    with_hooks: bool = False,
    with_agents_md: bool = False,
    force: bool = False,
) -> dict:
    repo = repo.resolve()
    harnesses = resolve_targets(target, repo, scope)
    actions: list[str] = []
    roots: dict[str, str] = {}
    guards: dict[str, str] = {}

    for harness in harnesses:
        destination = config_root(harness, repo, scope)
        roots[harness] = str(destination)
        assets = list(SHARED_ASSETS) + list(CLAUDE_ASSETS if harness == "claude" else OMP_ASSETS)
        if with_hooks:
            assets += list(CLAUDE_HOOKS if harness == "claude" else OMP_HOOKS)
        for relative_source, relative_target in assets:
            source = INTEGRATIONS / relative_source
            if not source.exists():
                raise ProtocolError(f"missing integration asset: {source}")
            actions.append(_copy(source, destination / relative_target, force))

        if with_hooks and harness == "claude":
            guard = destination / "hooks/handoff_guard.py"
            guard.chmod(0o755)
            command = f"python3 {guard}" if scope == "user" else GUARD_COMMAND
            actions.append(_merge_hooks(destination / "settings.json", command, GUARD_MATCHER))
            guards["claude"] = command
        elif with_hooks:
            guards["omp"] = f"{destination}/hooks/pre/handoff_guard.ts (discovered by path)"

        pointer = destination / "agent-team-ledger" / "protocol-root.txt"
        pointer.parent.mkdir(parents=True, exist_ok=True)
        pointer.write_text(f"{ROOT}\n", encoding="utf-8")
        actions.append(f"wrote {pointer}")

    snippet = INTEGRATIONS / AGENTS_SNIPPET
    if with_agents_md:
        for harness, root in roots.items():
            actions.append(_copy(snippet, Path(root) / "agent-team-ledger" / "AGENTS.snippet.md", force))

    primary = roots.get("claude") or roots[harnesses[0]]
    return {
        "scope": scope,
        "targets": harnesses,
        "roots": roots,
        "guards": guards,
        "protocol_root": str(ROOT),
        "actions": actions,
        "agents_snippet": str(snippet),
        "next_step": (
            f"paste {snippet} into the project AGENTS.md or CLAUDE.md, then run: "
            f"python {ROOT / 'scripts/agent_team.py'} init --repo {repo}"
        ),
        "claude_root": primary,
    }
