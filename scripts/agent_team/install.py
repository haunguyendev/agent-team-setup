"""Install the ledger protocol wiring into a coding agent configuration.

Claude Code reads skills, subagents and commands from ``<project>/.claude`` or
``~/.claude``. Installation is additive: existing files are never overwritten
unless ``--force`` is passed, and ``settings.json`` is edited only behind
``--with-hooks``, after writing a timestamped backup.
"""
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

from core.protocol import ProtocolError

ROOT = Path(__file__).resolve().parents[2]
INTEGRATIONS = ROOT / "integrations"
CLAUDE_ASSETS = (
    ("claude-code/skills/agent-team-ledger/SKILL.md", "skills/agent-team-ledger/SKILL.md"),
    ("claude-code/agents/agent-team-coordinator.md", "agents/agent-team-coordinator.md"),
    ("claude-code/agents/agent-team-worker.md", "agents/agent-team-worker.md"),
    ("claude-code/agents/agent-team-verifier.md", "agents/agent-team-verifier.md"),
    ("claude-code/commands/agent-team.md", "commands/agent-team.md"),
)
HOOK_ASSETS = (("claude-code/hooks/handoff_guard.py", "hooks/handoff_guard.py"),)
AGENTS_SNIPPET = "agents-md/AGENTS.snippet.md"
GUARD_COMMAND = 'python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/handoff_guard.py"'
GUARD_MATCHER = "Write|Edit|MultiEdit|NotebookEdit"


def claude_root(repo: Path, scope: str) -> Path:
    if scope == "user":
        return Path.home() / ".claude"
    if scope != "project":
        raise ProtocolError("scope must be 'project' or 'user'")
    return repo / ".claude"


def _copy(source: Path, target: Path, force: bool) -> str:
    if target.exists() and not force:
        return f"kept existing {target}"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return f"wrote {target}"


def _merge_hooks(settings: Path, command: str, matcher: str) -> str:
    settings.parent.mkdir(parents=True, exist_ok=True)
    existing: dict = {}
    if settings.exists():
        try:
            existing = json.loads(settings.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise ProtocolError(f"{settings} is not valid JSON: {error}") from error
        shutil.copy2(settings, settings.with_suffix(settings.suffix + f".bak-{int(time.time())}"))
    hooks = existing.setdefault("hooks", {})
    pre = hooks.setdefault("PreToolUse", [])
    if command in _registered_commands(pre):
        return f"hook already registered in {settings}"
    pre.append({"matcher": matcher, "hooks": [{"type": "command", "command": command}]})
    settings.write_text(json.dumps(existing, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return f"registered handoff guard in {settings}"


def _registered_commands(pre_tool_use: list) -> list[str]:
    return [
        hook.get("command")
        for entry in pre_tool_use
        if isinstance(entry, dict)
        for hook in entry.get("hooks", [])
        if isinstance(hook, dict)
    ]


def install(
    repo: Path,
    scope: str = "project",
    with_hooks: bool = False,
    with_agents_md: bool = False,
    force: bool = False,
) -> dict:
    repo = repo.resolve()
    destination = claude_root(repo, scope)
    actions: list[str] = []
    assets = list(CLAUDE_ASSETS)
    if with_hooks:
        assets += list(HOOK_ASSETS)
    for relative_source, relative_target in assets:
        source = INTEGRATIONS / relative_source
        if not source.exists():
            raise ProtocolError(f"missing integration asset: {source}")
        actions.append(_copy(source, destination / relative_target, force))
    if with_hooks:
        guard = destination / "hooks/handoff_guard.py"
        if guard.exists():
            guard.chmod(0o755)
        command = (
            f"python3 {guard}" if scope == "user" else f'python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/handoff_guard.py"'
        )
        actions.append(_merge_hooks(destination / "settings.json", command, GUARD_MATCHER))
    root_pointer = destination / "agent-team-ledger" / "protocol-root.txt"
    root_pointer.parent.mkdir(parents=True, exist_ok=True)
    root_pointer.write_text(f"{ROOT}\n", encoding="utf-8")
    actions.append(f"wrote {root_pointer}")
    snippet_target = destination / "agent-team-ledger" / "AGENTS.snippet.md"
    if with_agents_md:
        actions.append(_copy(INTEGRATIONS / AGENTS_SNIPPET, snippet_target, force))
    return {
        "scope": scope,
        "claude_root": str(destination),
        "protocol_root": str(ROOT),
        "actions": actions,
        "agents_snippet": str(snippet_target) if with_agents_md else str(INTEGRATIONS / AGENTS_SNIPPET),
        "next_step": (
            f"paste {snippet_target if with_agents_md else INTEGRATIONS / AGENTS_SNIPPET} "
            "into the project AGENTS.md or CLAUDE.md, then run: "
            f"python {ROOT / 'scripts/agent_team.py'} init --repo {repo}"
        ),
    }
