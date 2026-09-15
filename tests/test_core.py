from pathlib import Path

import pytest

from core.lanes import LaneJournal, LaneRequest
from core.protocol import ProtocolError, validate_result


def result():
    return {
        "task_id": "T-test",
        "outcome": "DONE",
        "plain_summary": "verified",
        "provenance": {
            "base_commit": "abc1234",
            "agent_model": "auto",
            "files_symbols": ["x"],
            "commands": [{"cmd": "true", "exit": 0}],
            "tests": [],
            "findings": [],
            "uncertainty": [],
        },
    }


def test_result_requires_complete_provenance():
    assert validate_result(result(), "T-test")["outcome"] == "DONE"
    broken = result()
    del broken["provenance"]["commands"]
    with pytest.raises(ProtocolError):
        validate_result(broken, "T-test")


def test_twenty_logical_lanes_and_idempotent_request(tmp_path: Path):
    journal = LaneJournal(tmp_path / "lanes.json", lanes=20)
    request = LaneRequest(19, "T-test", 0, "req-1", "hash")
    journal.put(request)
    journal.put(request)
    journal.retry("req-1", "429")
    journal.complete("req-1")
    assert journal.records["req-1"]["status"] == "complete"


def test_lane_boundary(tmp_path: Path):
    journal = LaneJournal(tmp_path / "lanes.json", lanes=20)
    with pytest.raises(ValueError):
        journal.put(LaneRequest(20, "T-test", 0, "req-1", "hash"))
