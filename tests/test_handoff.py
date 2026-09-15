"""End-to-end contract tests: publish → verify → promote, and every veto path."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from core.ledger import Ledger
from core.protocol import ProtocolError
from scripts.agent_team import store, verify as verifier

ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "integrations" / "claude-code" / "hooks" / "handoff_guard.py"


def run(cwd: Path, *args: str) -> str:
    proc = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True)
    assert proc.returncode == 0, f"git {' '.join(args)} failed: {proc.stderr}"
    return proc.stdout.strip()


def make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "main"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main", str(repo)], capture_output=True, check=True)
    run(repo, "config", "user.email", "tester@example.com")
    run(repo, "config", "user.name", "Tester")
    (repo / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    run(repo, "add", "-A")
    run(repo, "commit", "-m", "base")
    return repo


def make_result(task_id: str, commands: list[dict], outcome: str = "DONE") -> dict:
    return {
        "task_id": task_id,
        "outcome": outcome,
        "plain_summary": "changed VALUE to 2 and proved it",
        "provenance": {
            "base_commit": "recorded-by-caller",
            "agent_model": "auto",
            "files_symbols": ["app.py:VALUE"],
            "commands": commands,
            "tests": [],
            "findings": [],
            "uncertainty": [],
        },
    }


def worker_attempt(repo: Path, tmp_path: Path, task_id: str, result: dict, name: str = "wt") -> tuple[Path, str, Path]:
    """Create a worktree, commit a change, and return (worktree, base_commit, result file)."""
    base = run(repo, "rev-parse", "HEAD")
    worktree = tmp_path / name
    run(repo, "worktree", "add", "-b", f"agent/{name}", str(worktree), base)
    (worktree / "app.py").write_text("VALUE = 2\n", encoding="utf-8")
    run(worktree, "add", "-A")
    run(worktree, "commit", "-m", f"{task_id}: change value")
    result["provenance"]["base_commit"] = base
    result_file = tmp_path / f"{name}-result.json"
    result_file.write_text(json.dumps(result), encoding="utf-8")
    return worktree, base, result_file


@pytest.fixture(autouse=True)
def isolated_handoffs(tmp_path, monkeypatch):
    monkeypatch.setenv(store.HANDOFF_ENV, str(tmp_path / "handoffs"))


def test_verified_attempt_is_promoted_and_closes_the_task(tmp_path: Path):
    repo = make_repo(tmp_path)
    ledger = Ledger(repo)
    ledger.init()
    ledger.add_task("flip the value")
    base = run(repo, "rev-parse", "HEAD")
    ledger.assign("T-001", "worker-a", 0, ["app.py"], base)

    worktree, base, result_file = worker_attempt(
        repo, tmp_path, "T-001", make_result("T-001", [{"cmd": "cat app.py", "exit": 0}])
    )
    manifest = store.publish(repo, worktree, "T-001", 0, result_file, base)

    assert manifest["files"] == [{"path": "app.py", "sha256": manifest["files"][0]["sha256"]}]
    assert manifest["patch_bytes"] > 0
    assert ledger.load()["tasks"]["T-001"]["status"] == "assigned"

    record = verifier.verify(repo, "T-001", 0)
    assert record["verdict"] == "accept"
    assert record["commands"][0]["actual_exit"] == 0

    from scripts.agent_team import promote

    promotion = promote.promote(repo, "T-001", 0)
    assert promotion["staged_files"] == ["app.py"]
    assert (repo / "app.py").read_text(encoding="utf-8") == "VALUE = 2\n"
    assert run(repo, "diff", "--cached", "--name-only") == "app.py"
    assert ledger.load()["tasks"]["T-001"]["status"] == "complete"
    assert (ledger.root / "promotions" / "T-001-0.json").is_file()


def test_diverging_command_vetoes_promotion(tmp_path: Path):
    repo = make_repo(tmp_path)
    worktree, base, result_file = worker_attempt(
        repo, tmp_path, "T-002", make_result("T-002", [{"cmd": "python3 -c import sys;sys.exit(3)", "exit": 0}])
    )
    store.publish(repo, worktree, "T-002", 0, result_file, base)

    record = verifier.verify(repo, "T-002", 0)
    assert record["verdict"] == "reject"
    assert record["reasons"], "a veto must carry numbered reasons"

    from scripts.agent_team import promote

    with pytest.raises(ProtocolError, match="vetoed"):
        promote.promote(repo, "T-002", 0)


def test_attempts_are_immutable_and_tampering_is_detected(tmp_path: Path):
    repo = make_repo(tmp_path)
    worktree, base, result_file = worker_attempt(
        repo, tmp_path, "T-003", make_result("T-003", [{"cmd": "cat app.py", "exit": 0}])
    )
    store.publish(repo, worktree, "T-003", 0, result_file, base)

    with pytest.raises(ProtocolError, match="already published"):
        store.publish(repo, worktree, "T-003", 0, result_file, base)

    published = store.attempt_path(repo, "T-003", 0) / "result.json"
    published.chmod(0o644)
    published.write_text("{}", encoding="utf-8")
    with pytest.raises(ProtocolError, match="manifest hash"):
        store.load_attempt(repo, "T-003", 0)


def test_worker_cannot_publish_from_the_main_checkout(tmp_path: Path):
    repo = make_repo(tmp_path)
    result_file = tmp_path / "r.json"
    result_file.write_text(json.dumps(make_result("T-004", [{"cmd": "true", "exit": 0}])), encoding="utf-8")

    with pytest.raises(ProtocolError, match="isolated worktree"):
        store.publish(repo, repo, "T-004", 0, result_file, run(repo, "rev-parse", "HEAD"))


def test_publish_requires_a_clean_worktree(tmp_path: Path):
    repo = make_repo(tmp_path)
    worktree, base, result_file = worker_attempt(
        repo, tmp_path, "T-005", make_result("T-005", [{"cmd": "true", "exit": 0}])
    )
    (worktree / "app.py").write_text("VALUE = 3\n", encoding="utf-8")

    with pytest.raises(ProtocolError, match="uncommitted changes"):
        store.publish(repo, worktree, "T-005", 0, result_file, base)


def test_untracked_scratch_files_are_recorded_not_silently_dropped(tmp_path: Path):
    repo = make_repo(tmp_path)
    worktree, base, result_file = worker_attempt(
        repo, tmp_path, "T-007", make_result("T-007", [{"cmd": "true", "exit": 0}])
    )
    (worktree / "scratch.log").write_text("noise\n", encoding="utf-8")

    manifest = store.publish(repo, worktree, "T-007", 0, result_file, base)
    assert manifest["untracked_not_in_patch"] == ["scratch.log"]

    with pytest.raises(ProtocolError, match="untracked files"):
        store.publish(repo, worktree, "T-007", 1, result_file, base, strict_untracked=True)


def test_failing_evidence_is_vetoed_even_when_truthfully_recorded(tmp_path: Path):
    repo = make_repo(tmp_path)
    worktree, base, result_file = worker_attempt(
        repo, tmp_path, "T-008", make_result("T-008", [{"cmd": "false", "exit": 1}])
    )
    store.publish(repo, worktree, "T-008", 0, result_file, base)

    record = verifier.verify(repo, "T-008", 0)
    assert record["verdict"] == "reject"
    assert record["commands"][0]["actual_exit"] == 1
    assert record["commands"][0]["divergence"].startswith("command failed with exit 1")
    assert "expected_failure" in record["reasons"][0]


def test_expected_failure_baseline_does_not_veto(tmp_path: Path):
    repo = make_repo(tmp_path)
    worktree, base, result_file = worker_attempt(
        repo, tmp_path, "T-009", make_result("T-009", [{"cmd": "false", "exit": 1, "expected_failure": True}])
    )
    store.publish(repo, worktree, "T-009", 0, result_file, base)

    assert verifier.verify(repo, "T-009", 0)["verdict"] == "accept"


def test_promotion_ignores_untracked_scratch_but_refuses_tracked_edits(tmp_path: Path):
    repo = make_repo(tmp_path)
    ledger = Ledger(repo)
    ledger.init()
    base = run(repo, "rev-parse", "HEAD")
    ledger.add_task("promotion preconditions", task_id="T-010")
    ledger.assign("T-010", "worker-a", 0, ["app.py"], base)
    worktree, base, result_file = worker_attempt(
        repo, tmp_path, "T-010", make_result("T-010", [{"cmd": "true", "exit": 0}])
    )
    store.publish(repo, worktree, "T-010", 0, result_file, base)
    verifier.verify(repo, "T-010", 0)

    from scripts.agent_team import promote

    (repo / "scratch.txt").write_text("noise\n", encoding="utf-8")
    promote.promote(repo, "T-010", 0)
    assert (repo / "app.py").read_text(encoding="utf-8") == "VALUE = 2\n"

    (repo / "app.py").write_text("VALUE = 77\n", encoding="utf-8")
    with pytest.raises(ProtocolError, match="uncommitted tracked changes"):
        promote.promote(repo, "T-010", 0)


def test_ledger_refuses_illegal_transitions_and_oversized_notes(tmp_path: Path):
    repo = make_repo(tmp_path)
    ledger = Ledger(repo)
    ledger.init()
    ledger.add_task("guarded")
    with pytest.raises(ProtocolError, match="illegal transition"):
        ledger.transition("T-001", "complete")
    with pytest.raises(ProtocolError, match="exceed"):
        ledger.append_note("x" * 8_001)


def test_reconcile_reports_unverified_attempts_without_deleting(tmp_path: Path):
    repo = make_repo(tmp_path)
    worktree, base, result_file = worker_attempt(
        repo, tmp_path, "T-006", make_result("T-006", [{"cmd": "cat app.py", "exit": 0}])
    )
    store.publish(repo, worktree, "T-006", 0, result_file, base)

    from scripts.agent_team.reconcile import report

    payload = report(repo, stale_hours=0.0)
    assert [entry["state"] for entry in payload["attempts"]] == ["intact"]
    assert payload["stale_attempts"][0]["task_id"] == "T-006"
    assert payload["unmerged_commits"][0]["commits"], "worker commits must be reported as unmerged"
    assert store.attempt_path(repo, "T-006", 0).is_dir(), "reconciliation must not delete anything"


def test_guard_hook_blocks_writes_outside_the_worker_worktree(tmp_path: Path):
    repo = make_repo(tmp_path)
    base = run(repo, "rev-parse", "HEAD")
    worktree = tmp_path / "wt-guard"
    run(repo, "worktree", "add", "-b", "agent/guard", str(worktree), base)

    blocked = subprocess.run(
        [sys.executable, str(GUARD)],
        input=json.dumps(
            {"tool_name": "Edit", "cwd": str(worktree), "tool_input": {"file_path": str(repo / "app.py")}}
        ),
        capture_output=True,
        text=True,
    )
    assert blocked.returncode == 2
    assert "must not write" in blocked.stderr

    allowed = subprocess.run(
        [sys.executable, str(GUARD)],
        input=json.dumps(
            {"tool_name": "Edit", "cwd": str(worktree), "tool_input": {"file_path": str(worktree / "app.py")}}
        ),
        capture_output=True,
        text=True,
    )
    assert allowed.returncode == 0

    coordinator = subprocess.run(
        [sys.executable, str(GUARD)],
        input=json.dumps({"tool_name": "Edit", "cwd": str(repo), "tool_input": {"file_path": str(repo / "app.py")}}),
        capture_output=True,
        text=True,
    )
    assert coordinator.returncode == 0
