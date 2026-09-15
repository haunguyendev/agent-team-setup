"""The hard demo stays fair: the acceptance harness must pass a reference solution and fail the stubs."""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "examples" / "hard-demo"


def run_check(tmp_path: Path, modules: Path) -> subprocess.CompletedProcess:
    work = tmp_path / "checkout"
    work.mkdir()
    shutil.copy2(DEMO / "check.py", work / "check.py")
    for module in ("pricing.py", "inventory.py", "orders.py"):
        shutil.copy2(modules / module, work / module)
    return subprocess.run(
        [sys.executable, "check.py"], cwd=str(work), capture_output=True, text=True
    )


def test_reference_solution_satisfies_the_harness(tmp_path: Path):
    result = run_check(tmp_path, DEMO / "reference-solution")
    assert result.returncode == 0, result.stdout
    assert "PASS" in result.stdout


def test_stub_seed_fails_every_section(tmp_path: Path):
    result = run_check(tmp_path, DEMO / "stubs")
    assert result.returncode == 1
    assert "FAIL (3)" in result.stdout
    for section in ("pricing", "inventory", "orders"):
        assert f"{section}: crashed" in result.stdout, section


def test_harness_sections_run_independently(tmp_path: Path):
    """A worker owns one module, so one section must be runnable on its own."""
    work = tmp_path / "checkout"
    work.mkdir()
    shutil.copy2(DEMO / "check.py", work / "check.py")
    shutil.copy2(DEMO / "reference-solution" / "pricing.py", work / "pricing.py")
    result = subprocess.run(
        [sys.executable, "check.py", "pricing"], cwd=str(work), capture_output=True, text=True
    )
    assert result.returncode == 0, result.stdout
    assert "PASS - pricing" in result.stdout
