"""Guard rule tests for OMP hook files, executed by bun when it is available."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BUN = shutil.which("bun")


@pytest.mark.skipif(BUN is None, reason="bun is required to exercise the TypeScript hook")
def test_omp_guard_decisions():
    proc = subprocess.run(
        [BUN, "run", str(ROOT / "tests" / "omp_guard.test.ts")],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
    assert "PASS" in proc.stdout


def test_omp_agent_definitions_carry_the_omp_contract():
    """OMP skips .claude/agents, so the native definitions must satisfy its parser."""
    agents = sorted((ROOT / "integrations" / "omp" / "agents").glob("*.md"))
    assert len(agents) == 3

    for path in agents:
        text = path.read_text(encoding="utf-8")
        assert text.startswith("---\n"), f"{path.name} needs frontmatter"
        frontmatter = text.split("---", 2)[1]
        assert f"name: {path.stem}" in frontmatter, f"{path.name} must declare its own name"
        assert "description:" in frontmatter
        assert "autoloadSkills: agent-team-ledger" in frontmatter, f"{path.name} must load the skill"
        assert len(text.split("---", 2)[2].strip()) > 200, f"{path.name} needs a real system prompt"

    coordinator = (ROOT / "integrations" / "omp" / "agents" / "agent-team-coordinator.md").read_text()
    assert "spawns: agent-team-worker, agent-team-verifier" in coordinator
    worker = (ROOT / "integrations" / "omp" / "agents" / "agent-team-worker.md").read_text()
    verifier = (ROOT / "integrations" / "omp" / "agents" / "agent-team-verifier.md").read_text()
    assert 'spawns: ""' in worker and 'spawns: ""' in verifier, "workers must not spawn further agents"
    assert "write" not in verifier.split("---", 2)[1].split("tools:")[1].split("\n")[0]
