"""Dream cycle state persistence.

Tracks last run timestamp, episode counts, and session pointers
so each cycle knows what's new since the last dream.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from hermes_constants import get_hermes_home  # type: ignore
except Exception:

    def get_hermes_home() -> Path:
        return Path.home() / ".hermes"


def state_path() -> Path:
    return Path(get_hermes_home()) / "zellandine" / "state.json"


def read_state() -> dict[str, Any]:
    """Read dream cycle state."""
    p = state_path()
    if not p.exists():
        return default_state()
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default_state()


def write_state(state: dict[str, Any]) -> None:
    """Persist dream cycle state."""
    p = state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def default_state() -> dict[str, Any]:
    return {
        "last_dream_at": None,
        "total_cycles": 0,
        "total_proposals": 0,
        "total_applied": 0,
        "total_reverted": 0,
        "recent_session_ids": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def record_cycle(
    *,
    artifact_id: str,
    episode_count: int = 0,
    proposal_count: int = 0,
    applied_count: int = 0,
    reverted_count: int = 0,
    session_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Update state after a dream cycle."""
    state = read_state()
    state["last_dream_at"] = datetime.now(timezone.utc).isoformat()
    state["total_cycles"] = state.get("total_cycles", 0) + 1
    state["total_proposals"] = state.get("total_proposals", 0) + proposal_count
    state["total_applied"] = state.get("total_applied", 0) + applied_count
    state["total_reverted"] = state.get("total_reverted", 0) + reverted_count
    if session_ids:
        state["recent_session_ids"] = session_ids[-50:]  # keep last 50
    write_state(state)
    return state
