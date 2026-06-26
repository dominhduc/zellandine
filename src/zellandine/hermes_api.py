"""Thin wrapper around Hermes' native subsystems.

Zellandine is "Hermes-native": it reads and writes through Hermes' own
storage and modules rather than maintaining a parallel store.

- Memory:   ~/.hermes/memories/{MEMORY,USER}.md  (entries split by "\n§\n")
             writes go through tools.memory_tool.MemoryStore (locking + drift checks)
- Sessions: ~/.hermes/state.db via hermes_state.SessionDB
- Skills:   ~/.hermes/skills/<name>/SKILL.md, patched via tools.skill_manager_tool
- Cron:     ~/.hermes/cron/jobs.json via cron.jobs.create_job; output in cron/output/

The native modules live in the hermes-agent checkout, which is added to
sys.path lazily so importing zellandine never hard-requires Hermes.
"""
from __future__ import annotations

import json
import logging
import re
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger("zellandine")

ENTRY_DELIMITER = "\n§\n"

try:
    from hermes_constants import get_hermes_home  # type: ignore
except Exception:

    def get_hermes_home() -> Path:
        return Path.home() / ".hermes"


def hermes_home() -> Path:
    return Path(get_hermes_home())


def hermes_agent_root() -> Path | None:
    """Locate the hermes-agent source checkout."""
    candidates = [
        hermes_home() / "hermes-agent",
        Path.home() / ".hermes" / "hermes-agent",
    ]
    for c in candidates:
        if (c / "hermes_state.py").exists():
            return c
    return None


def ensure_hermes_path() -> bool:
    """Add the hermes-agent checkout to sys.path. Returns True if available."""
    root = hermes_agent_root()
    if root is None:
        return False
    s = str(root)
    if s not in sys.path:
        sys.path.insert(0, s)
    return True


# --- Memory (read) -------------------------------------------------------

def _memory_dir() -> Path:
    return hermes_home() / "memories"


def _parse_entries(text: str) -> list[str]:
    return [e.strip() for e in text.split(ENTRY_DELIMITER) if e.strip()]


def read_memory() -> dict[str, list[str]]:
    """Read current memory + user-profile entries from the markdown stores."""
    out: dict[str, list[str]] = {"memory": [], "user": []}
    mem = _memory_dir() / "MEMORY.md"
    usr = _memory_dir() / "USER.md"
    if mem.exists():
        out["memory"] = _parse_entries(mem.read_text(encoding="utf-8"))
    if usr.exists():
        out["user"] = _parse_entries(usr.read_text(encoding="utf-8"))
    return out


def memory_context_block() -> dict[str, str]:
    """Render memory state for an LLM prompt (numbered entries)."""
    mem = read_memory()
    def fmt(entries: list[str]) -> str:
        return "\n".join(f"- {e}" for e in entries) if entries else "(empty)"
    return {"memory": fmt(mem["memory"]), "user": fmt(mem["user"])}


# --- Sessions (read) -----------------------------------------------------

def _open_session_db(read_only: bool = True):
    if not ensure_hermes_path():
        return None
    try:
        from hermes_state import SessionDB  # type: ignore

        return SessionDB(read_only=read_only)
    except Exception as exc:  # pragma: no cover - depends on live env
        logger.warning("SessionDB unavailable: %s", exc)
        return None


def read_session_digests(limit: int = 14) -> list[dict[str, Any]]:
    """Read compact digests of recent root/branch sessions via SessionDB.

    Falls back to a direct SQLite read if SessionDB import fails.
    """
    db = _open_session_db(read_only=True)
    if db is not None:
        try:
            rows = db.list_sessions_rich(
                exclude_sources=["subagent", "tool", "cron"],
                limit=limit,
                min_message_count=2,
            )
            digests = []
            for r in rows:
                sid = r.get("id")
                # list_sessions_rich gives correct lineage/metadata; pull fuller
                # user-message content via a read-only query (previews are ~80c).
                turns = _user_turns_sqlite(sid)
                digests.append(
                    {
                        "session_id": sid,
                        "title": r.get("title"),
                        "started_at": r.get("started_at"),
                        "message_count": r.get("message_count") or 0,
                        "source": r.get("source") or "unknown",
                        "user_turns": turns,
                    }
                )
            return digests
        except Exception as exc:
            logger.warning("list_sessions_rich failed (%s); falling back", exc)
        finally:
            try:
                db.close()
            except Exception:
                pass
    return _read_sessions_sqlite(limit)


def _user_turns_sqlite(session_id: str, limit: int = 6) -> list[str]:
    """Read the first N user-message contents for a session (read-only)."""
    import sqlite3

    db_path = hermes_home() / "state.db"
    if not db_path.exists() or not session_id:
        return []
    try:
        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
            rows = conn.execute(
                "SELECT content FROM messages WHERE session_id = ? "
                "AND role = 'user' AND active = 1 AND content IS NOT NULL "
                "ORDER BY timestamp LIMIT ?",
                (session_id, limit),
            ).fetchall()
        turns = []
        for (content,) in rows:
            if not content:
                continue
            # Skip system-injected reply-quote prefixes' noise but keep the gist.
            text = content.strip()
            if len(text) > 10:
                turns.append(text[:500])
        return turns
    except Exception:
        return []


def _read_sessions_sqlite(limit: int) -> list[dict[str, Any]]:
    import sqlite3

    db_path = hermes_home() / "state.db"
    if not db_path.exists():
        logger.warning("Session DB not found at %s", db_path)
        return []
    try:
        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT id, title, started_at, message_count, source
                FROM sessions
                WHERE source NOT IN ('subagent','tool','cron')
                  AND message_count >= 2
                ORDER BY started_at DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            digests = []
            for row in rows:
                sid = row["id"]
                msg_rows = conn.execute(
                    "SELECT content FROM messages WHERE session_id = ? "
                    "AND role = 'user' AND active = 1 ORDER BY timestamp LIMIT 6",
                    (sid,),
                ).fetchall()
                turns = [
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
                        "user_turns": turns,
                    }
                )
            return digests
    except Exception as exc:
        logger.error("Failed to read sessions: %s", exc)
        return []


# --- Cron output (read) --------------------------------------------------

def read_cron_outputs(lookback_hours: int = 24, max_files: int = 40) -> list[dict[str, Any]]:
    """Scan recent cron output markdown files for errors/anomalies.

    Returns the most recent run per job plus any that contain error markers.
    """
    out_dir = hermes_home() / "cron" / "output"
    if not out_dir.exists():
        return []
    results: list[dict[str, Any]] = []
    files = sorted(
        out_dir.rglob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True
    )[:max_files]
    for f in files:
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        job = f.parent.name
        name_match = re.search(r"# Cron Job:\s*(.+)", text)
        name = name_match.group(1).strip() if name_match else job
        lowered = text.lower()
        has_error = any(
            marker in lowered
            for marker in ("traceback", "error:", "failed", "exception", "exit code")
        )
        results.append(
            {
                "job_id": job,
                "name": name,
                "path": str(f),
                "mtime": f.stat().st_mtime,
                "has_error": has_error,
                "excerpt": text[:600],
            }
        )
    return results


# --- Skills (read) -------------------------------------------------------

def read_skill_list() -> list[dict[str, str]]:
    """List installed Hermes skills with names and descriptions."""
    skills_dir = hermes_home() / "skills"
    if not skills_dir.exists():
        return []
    skills = []
    for skill_md in skills_dir.rglob("SKILL.md"):
        try:
            content = skill_md.read_text(encoding="utf-8")
            name = skill_md.parent.name
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


def skill_context_block() -> str:
    skills = read_skill_list()
    if not skills:
        return "(none)"
    return "\n".join(f"- {s['name']}: {s['description']}" for s in skills)


# --- Writes / apply (mutating — used only by `apply`, never by `run`) ----

def snapshot_memory(backup_dir: Path) -> list[str]:
    """Copy the memory markdown files into a backup dir. Returns copied names."""
    backup_dir.mkdir(parents=True, exist_ok=True)
    copied = []
    for fname in ("MEMORY.md", "USER.md"):
        src = _memory_dir() / fname
        if src.exists():
            (backup_dir / fname).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
            copied.append(fname)
    return copied


def restore_memory(backup_dir: Path) -> list[str]:
    """Restore memory markdown files from a backup dir."""
    restored = []
    for fname in ("MEMORY.md", "USER.md"):
        src = backup_dir / fname
        if src.exists():
            (_memory_dir() / fname).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
            restored.append(fname)
    return restored


def _memory_store():
    if not ensure_hermes_path():
        raise RuntimeError("hermes-agent not available — cannot mutate memory")
    from tools.memory_tool import MemoryStore  # type: ignore

    store = MemoryStore()
    store.load_from_disk()
    return store


def apply_memory(action: str, target: str, content: str, old_text: str | None = None) -> dict[str, Any]:
    """Apply a memory mutation through the native MemoryStore.

    target: "memory" | "user"; action: "add" | "replace" | "remove".
    """
    store = _memory_store()
    if action == "add":
        return store.add(target, content)
    if action == "replace":
        return store.replace(target, old_text or "", content)
    if action == "remove":
        return store.remove(target, old_text or content)
    raise ValueError(f"unsupported memory action: {action}")


def apply_skill_patch(
    skill_name: str, old_string: str, new_string: str, replace_all: bool = False
) -> dict[str, Any]:
    """Patch a skill's SKILL.md through the native skill_manage tool."""
    if not ensure_hermes_path():
        raise RuntimeError("hermes-agent not available — cannot patch skills")
    from tools.skill_manager_tool import skill_manage  # type: ignore

    result = skill_manage(
        action="patch",
        name=skill_name,
        old_string=old_string,
        new_string=new_string,
        replace_all=replace_all,
    )
    try:
        return json.loads(result)
    except Exception:
        return {"raw": result}


def create_cron_job(*, name: str, schedule: str, script: str, deliver: str = "telegram") -> dict[str, Any]:
    """Register a script-only (no LLM) nightly cron job in Hermes."""
    if not ensure_hermes_path():
        raise RuntimeError("hermes-agent not available — cannot create cron job")
    from cron.jobs import create_job  # type: ignore

    return create_job(
        prompt=None,
        schedule=schedule,
        name=name,
        deliver=deliver,
        script=script,
        no_agent=True,
    )
