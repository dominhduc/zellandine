"""Thin wrapper around Hermes native APIs.

This module abstracts the calls to Hermes' memory(), skill_manage(),
and session_search() tools so the dream cycle can use them without
importing Hermes internals directly.

In a live Hermes session, these calls go through the tool system.
In standalone/script mode, they call the Hermes CLI or SQLite directly.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any

logger = logging.getLogger("zellandine")

try:
    from hermes_constants import get_hermes_home  # type: ignore
except Exception:

    def get_hermes_home() -> Path:
        return Path.home() / ".hermes"


def _hermes_db() -> Path:
    """Locate the Hermes session database."""
    home = Path(get_hermes_home())
    candidates = [home / "state.db", home / "sessions" / "sessions.db"]
    for c in candidates:
        if c.exists():
            return c
    return home / "state.db"


def read_memory() -> dict[str, Any]:
    """Read current memory state from Hermes.

    Returns {'memory': [...], 'user': [...]}.
    """
    # In live session: would call memory(action=read) via tool system
    # In script mode: read from Hermes state files
    home = Path(get_hermes_home())
    result: dict[str, Any] = {"memory": [], "user": []}

    # TODO: Implement actual memory reading
    # Hermes stores memory internally — the tool API is the canonical reader
    return result


def read_session_digests(limit: int = 14) -> list[dict[str, Any]]:
    """Read compact digests of recent sessions.

    Uses a fallback chain:
    1. hermes_state.SessionDB (if available)
    2. Direct SQLite read
    3. Empty list (graceful degradation)
    """
    db_path = _hermes_db()
    if not db_path.exists():
        logger.warning("Session DB not found at %s", db_path)
        return []

    try:
        with sqlite3.connect(str(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT s.id, s.title, s.started_at, s.message_count, s.source
                FROM sessions s
                WHERE s.parent_session_id IS NULL OR EXISTS (
                    SELECT 1 FROM sessions p
                    WHERE p.id = s.parent_session_id AND p.end_reason = 'branched'
                )
                ORDER BY s.started_at DESC, s.id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

            digests = []
            for row in rows:
                sid = row["id"]
                # Get user messages
                msg_rows = conn.execute(
                    "SELECT role, content FROM messages WHERE session_id = ? "
                    "AND role = 'user' ORDER BY timestamp LIMIT 6",
                    (sid,),
                ).fetchall()
                user_turns = [
                    r["content"][:400]
                    for r in msg_rows
                    if r["content"] and len(r["content"]) > 10
                ]
                digests.append(
                    {
                        "session_id": sid,
                        "title": row["title"],
                        "started_at": row["started_at"],
                        "message_count": row["message_count"] or 0,
                        "source": row["source"] or "sqlite",
                        "user_turns": user_turns,
                    }
                )
            return digests
    except Exception as exc:
        logger.error("Failed to read sessions: %s", exc)
        return []


def read_cron_outputs(lookback_hours: int = 24) -> list[dict[str, Any]]:
    """Read recent cron job outputs for errors and anomalies."""
    home = Path(get_hermes_home())
    cron_output = home / "cron" / "output"
    if not cron_output.exists():
        return []

    results = []
    # TODO: Implement — walk cron output directories, read .md files,
    # extract job name, status, errors
    return results


def read_skill_list() -> list[dict[str, str]]:
    """List installed Hermes skills with names and descriptions."""
    home = Path(get_hermes_home())
    skills_dir = home / "skills"
    if not skills_dir.exists():
        return []

    skills = []
    # Walk skill directories looking for SKILL.md files
    for skill_md in skills_dir.rglob("SKILL.md"):
        try:
            content = skill_md.read_text(encoding="utf-8")
            name = skill_md.parent.name
            # Extract description from YAML frontmatter
            desc = ""
            if content.startswith("---"):
                end = content.find("---", 3)
                if end > 0:
                    for line in content[3:end].splitlines():
                        if line.strip().startswith("description:"):
                            desc = line.split(":", 1)[1].strip().strip('"').strip("'")
                            break
            skills.append({"name": name, "description": desc, "path": str(skill_md)})
        except Exception:
            continue
    return skills
