"""Canonical serialisation and digests for handoff payloads.

Deterministic bytes are the whole point: the marker digest must be reproducible
by anyone who has the payload, so tampering is detectable without trusting the
filesystem's write permissions.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

HANDOFF_ENV = "CLAUDE_AGENT_HANDOFF_ROOT"
DEFAULT_HANDOFF_ROOT = Path.home() / ".claude-camel" / "handoffs"
PROTOCOL_VERSION = 1
PAYLOAD_FILES = ("result.json", "change.patch", "manifest.json", "MARKER")
VERIFICATION_FILE = "verification.json"


def stamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(value: Any) -> bytes:
    return json.dumps(value, indent=2, sort_keys=True).encode("utf-8")


def marker_digest(manifest: dict[str, Any], result_sha: str) -> str:
    return sha256(canonical({"manifest": manifest, "result_sha256": result_sha}))
