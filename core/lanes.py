"""Durable logical-lane state; backend throttling never changes lane identity."""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .protocol import atomic_json


@dataclass
class LaneRequest:
    lane_id: int
    task_id: str
    attempt: int
    request_id: str
    payload_sha256: str
    retries: int = 0
    next_eligible_at: float = 0.0
    status: str = "queued"
    backend_status: str | None = None


class LaneJournal:
    def __init__(self, path: Path, lanes: int = 20) -> None:
        if lanes < 1:
            raise ValueError("lanes must be positive")
        self.path = path
        self.lanes = lanes
        self.records: dict[str, dict[str, Any]] = {}

    def put(self, request: LaneRequest) -> None:
        if not 0 <= request.lane_id < self.lanes:
            raise ValueError("lane_id outside configured logical lanes")
        prior = self.records.get(request.request_id)
        if prior and prior.get("payload_sha256") != request.payload_sha256:
            raise ValueError("request_id reused with a different payload")
        self.records[request.request_id] = asdict(request)
        self.flush()

    def retry(self, request_id: str, status: str, base_delay: float = 1.0) -> None:
        record = self.records[request_id]
        record["retries"] += 1
        record["backend_status"] = status
        record["status"] = "waiting"
        record["next_eligible_at"] = time.time() + min(300.0, base_delay * (2 ** min(record["retries"], 8)))
        self.flush()

    def complete(self, request_id: str, status: str = "complete") -> None:
        self.records[request_id]["status"] = status
        self.records[request_id]["backend_status"] = status
        self.flush()

    def flush(self) -> None:
        atomic_json(self.path, {"version": 1, "logical_lanes": self.lanes, "requests": self.records})
