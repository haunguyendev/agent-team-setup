"""Portable coordination primitives for Claude Code agent teams."""

from .protocol import (
    OUTCOMES,
    ProtocolError,
    atomic_json,
    repo_identity,
    validate_result,
)

__all__ = ["OUTCOMES", "ProtocolError", "atomic_json", "repo_identity", "validate_result"]
