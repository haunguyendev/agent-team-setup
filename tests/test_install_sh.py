"""The quick-install script must be idempotent and must not touch the real agent config."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "install.sh"
BASH = shutil.which("bash")

pytestmark = pytest.mark.skipif(BASH is None, reason="bash is required")


def install(home: Path, *args: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "HOME": str(home)}
    return subprocess.run(
        [str(BASH), str(SCRIPT), *args],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(ROOT),
    )


def hook_commands(settings: Path) -> list[str]:
    payload = json.loads(settings.read_text(encoding="utf-8"))
    return [hook["command"] for group in payload["hooks"]["PreToolUse"] for hook in group["hooks"]]


def test_global_install_wires_every_agent_asset(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    result = install(home)
    assert result.returncode == 0, result.stderr

    claude = home / ".claude"
    for relative in (
        "skills/agent-team-ledger/SKILL.md",
        "agents/agent-team-worker.md",
        "agents/agent-team-coordinator.md",
        "agents/agent-team-verifier.md",
        "commands/agent-team.md",
        "hooks/handoff_guard.py",
    ):
        assert (claude / relative).is_file(), relative
    assert (claude / "agent-team-ledger" / "protocol-root.txt").read_text().strip() == str(ROOT)
    (command,) = hook_commands(claude / "settings.json")
    assert command == f"python3 {claude / 'hooks/handoff_guard.py'}", "global hook must be absolute"
    assert Path(command.split(" ", 1)[1]).is_file()


def test_reinstall_is_idempotent_and_check_mode_passes(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    assert install(home).returncode == 0
    assert install(home, "--quiet").returncode == 0
    assert len(hook_commands(home / ".claude" / "settings.json")) == 1

    checked = install(home, "--check")
    assert checked.returncode == 0, checked.stderr
    assert "global wiring present" in checked.stdout


def test_project_install_targets_the_given_directory(tmp_path: Path):
    home = tmp_path / "home"
    project = tmp_path / "project"
    home.mkdir()
    project.mkdir()

    result = install(home, "--project", str(project))
    assert result.returncode == 0, result.stderr
    assert (project / ".claude" / "skills/agent-team-ledger/SKILL.md").is_file()
    (command,) = hook_commands(project / ".claude" / "settings.json")
    assert command == 'python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/handoff_guard.py"'
    assert not (home / ".claude").exists(), "a project install must not touch the global config"


def test_unknown_option_fails_loudly(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    result = install(home, "--does-not-exist")
    assert result.returncode == 1
    assert "unknown option" in result.stderr
    assert not (home / ".claude").exists()
