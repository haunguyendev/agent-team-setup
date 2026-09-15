"""Installer contract: assets land where the agent reads them, per harness and scope."""
from __future__ import annotations

import json
from pathlib import Path

from scripts.agent_team import install as installer

CLAUDE_PROJECT_FILES = (
    "skills/agent-team-ledger/SKILL.md",
    "commands/agent-team.md",
    "agents/agent-team-coordinator.md",
    "agents/agent-team-worker.md",
    "agents/agent-team-verifier.md",
    "agent-team-ledger/protocol-root.txt",
)
OMP_PROJECT_FILES = (
    "skills/agent-team-ledger/SKILL.md",
    "commands/agent-team.md",
    "agents/agent-team-coordinator.md",
    "agents/agent-team-worker.md",
    "agents/agent-team-verifier.md",
    "hooks/pre/handoff_guard.ts",
    "agent-team-ledger/protocol-root.txt",
)


def _hook_commands(settings: Path) -> list[str]:
    payload = json.loads(settings.read_text(encoding="utf-8"))
    return [entry["command"] for group in payload["hooks"]["PreToolUse"] for entry in group["hooks"]]


def test_project_install_writes_assets_and_a_project_relative_hook(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    result = installer.install(repo, scope="project", target="claude", with_hooks=True, with_agents_md=True)

    root = Path(result["roots"]["claude"])
    assert root == repo / ".claude"
    for relative in CLAUDE_PROJECT_FILES:
        assert (root / relative).is_file(), relative
    assert (root / "agent-team-ledger" / "AGENTS.snippet.md").is_file()
    assert (root / "hooks" / "handoff_guard.py").stat().st_mode & 0o111, "hook must be executable"
    pointer = Path((root / "agent-team-ledger" / "protocol-root.txt").read_text().strip())
    assert (pointer / "scripts" / "agent_team" / "handoff.py").is_file(), "protocol-root must point at $P"
    assert _hook_commands(root / "settings.json") == [installer.GUARD_COMMAND]


def test_user_install_registers_an_absolute_hook_because_project_dir_differs(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    repo = tmp_path / "repo"
    repo.mkdir()

    result = installer.install(repo, scope="user", target="claude", with_hooks=True)

    root = Path(result["roots"]["claude"])
    assert root == home / ".claude"
    (command,) = _hook_commands(root / "settings.json")
    assert "$CLAUDE_PROJECT_DIR" not in command, "a user-scope hook must not depend on the project directory"
    assert command == f"python3 {root / 'hooks/handoff_guard.py'}"
    assert Path(command.split(" ", 1)[1]).is_file()


def test_omp_install_uses_native_paths_and_needs_no_settings_entry(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    result = installer.install(repo, scope="project", target="omp", with_hooks=True)

    root = Path(result["roots"]["omp"])
    assert root == repo / ".omp"
    for relative in OMP_PROJECT_FILES:
        assert (root / relative).is_file(), relative
    assert not (root / "settings.json").exists(), "OMP discovers hooks by path, not from settings"
    assert "handoff_guard.ts" in result["guards"]["omp"]


def test_auto_target_installs_omp_only_where_it_exists(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    repo = tmp_path / "repo"
    repo.mkdir()

    assert installer.install(repo, scope="project")["targets"] == ["claude"]

    (repo / ".omp").mkdir()
    assert installer.install(repo, scope="project")["targets"] == ["claude", "omp"]

    assert installer.install(repo, scope="project", target="both")["targets"] == ["claude", "omp"]


def test_install_keeps_existing_assets_and_backs_up_settings(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    first = installer.install(repo, scope="project", target="claude")
    skill = Path(first["roots"]["claude"]) / "skills/agent-team-ledger/SKILL.md"
    skill.write_text("hand edited\n", encoding="utf-8")

    second = installer.install(repo, scope="project", target="claude", with_hooks=True)
    assert skill.read_text(encoding="utf-8") == "hand edited\n", "existing files are kept without --force"
    assert any(action.startswith("kept existing") for action in second["actions"])

    settings = Path(second["roots"]["claude"]) / "settings.json"
    before = json.loads(settings.read_text(encoding="utf-8"))
    installer.install(repo, scope="project", target="claude", with_hooks=True)
    assert json.loads(settings.read_text(encoding="utf-8")) == before, "re-install must not duplicate the hook"
    assert list(settings.parent.glob("settings.json.bak-*")), "settings.json must be backed up before merging"
