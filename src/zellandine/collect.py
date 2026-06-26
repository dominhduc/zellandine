"""Stage 1 — Collect (Sleep Onset / Hippocampal Replay)

Gather raw material from recent Hermes sessions and cron outputs.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(slots=True, eq=True)
class Episode:
    """A salient event extracted from a session or cron run."""

    source: str
    timestamp: str
    type: str  # correction | decision | error | preference | task | info
    content: str
    severity: str = "normal"  # low | normal | high
    existing_memory_match: str | None = None
    session_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "timestamp": self.timestamp,
            "type": self.type,
            "content": self.content,
            "severity": self.severity,
            "existing_memory_match": self.existing_memory_match,
            "session_id": self.session_id,
        }


@dataclass
class CollectionResult:
    """Output of Stage 1 — episodes ready for consolidation."""

    episodes: list[Episode] = field(default_factory=list)
    session_count: int = 0
    cron_errors: list[str] = field(default_factory=list)
    collected_at: str = ""

    def __post_init__(self) -> None:
        if not self.collected_at:
            self.collected_at = datetime.now(timezone.utc).isoformat()

    def to_prompt_block(self) -> str:
        """Render for inclusion in a consolidation LLM prompt."""
        if not self.episodes:
            return "No episodes collected.\n"

        lines = [
            f"### Collected episodes ({len(self.episodes)} from {self.session_count} sessions)",
            "",
        ]
        for i, ep in enumerate(self.episodes, 1):
            lines.append(
                f"{i}. **[{ep.type}]** {ep.content} "
                f"_(source: {ep.source}, severity: {ep.severity})_"
            )
            if ep.existing_memory_match:
                lines.append(f"   → Related memory: {ep.existing_memory_match}")

        if self.cron_errors:
            lines.append("")
            lines.append(f"### Cron errors ({len(self.cron_errors)})")
            for err in self.cron_errors:
                lines.append(f"- {err}")

        return "\n".join(lines) + "\n"


# Heuristic cues for classifying a user turn into an episode type.
# Ordered by priority — first match wins.
_CLASSIFIERS: list[tuple[str, tuple[str, ...]]] = [
    ("correction", (
        "no.", "no,", "not ", "don't", "do not", "never", "stop ", "wrong",
        "actually", "instead", "i said", "i told you", "again", "incorrect",
        "không phải", "đừng", "sai", "lại", "đã bảo",
    )),
    ("preference", (
        "i prefer", "i like", "i want", "always ", "from now", "please use",
        "i'd rather", "make sure", "remember", "tôi muốn", "tôi thích", "nhớ",
    )),
    ("decision", (
        "let's ", "we'll ", "go with", "decided", "use ", "build ", "create ",
        "i'll ", "we call this", "name it", "move ", "draft",
    )),
    ("task", (
        "can you", "could you", "please ", "run ", "find ", "fix ", "add ",
        "implement", "write ", "check ", "look ", "set up", "help me",
    )),
]


def _classify(text: str) -> tuple[str, str]:
    """Return (episode_type, severity) for a user turn."""
    low = text.lower()
    for etype, cues in _CLASSIFIERS:
        if any(cue in low for cue in cues):
            severity = "high" if etype == "correction" else "normal"
            return etype, severity
    return "info", "low"


def _match_existing_memory(text: str, memory_entries: list[str]) -> str | None:
    """Crude overlap match: does an existing memory entry share salient words?"""
    words = {w for w in re.findall(r"[a-zA-Z]{5,}", text.lower())}
    if not words:
        return None
    best, best_overlap = None, 0
    for entry in memory_entries:
        ewords = {w for w in re.findall(r"[a-zA-Z]{5,}", entry.lower())}
        overlap = len(words & ewords)
        if overlap > best_overlap:
            best, best_overlap = entry, overlap
    return best[:160] if best and best_overlap >= 3 else None


def collect(
    session_limit: int = 14,
    *,
    hermes_home: Path | None = None,
) -> CollectionResult:
    """Collect episodes from recent Hermes sessions and cron outputs.

    Stage 1 (Sleep Onset): read recent sessions + cron output, extract salient
    user turns, classify them, and note matches against existing memory.
    """
    from . import hermes_api

    memory = hermes_api.read_memory()
    mem_entries = memory.get("memory", []) + memory.get("user", [])

    digests = hermes_api.read_session_digests(limit=session_limit)
    episodes: list[Episode] = []
    for d in digests:
        sid = d.get("session_id")
        ts = _coerce_ts(d.get("started_at"))
        for turn in d.get("user_turns", []):
            turn = _clean_turn(turn)
            if len(turn) < 12:
                continue
            etype, severity = _classify(turn)
            episodes.append(
                Episode(
                    source=f"session:{sid}",
                    timestamp=ts,
                    type=etype,
                    content=turn,
                    severity=severity,
                    existing_memory_match=_match_existing_memory(turn, mem_entries),
                    session_id=sid,
                )
            )

    cron_errors: list[str] = []
    for c in hermes_api.read_cron_outputs():
        if c.get("has_error"):
            cron_errors.append(
                f"{c.get('name')} ({c.get('job_id')}): error in {c.get('path')}"
            )
            episodes.append(
                Episode(
                    source=f"cron:{c.get('job_id')}",
                    timestamp=datetime.fromtimestamp(
                        c.get("mtime", 0), timezone.utc
                    ).isoformat(),
                    type="error",
                    content=(
                        f"Cron job '{c.get('name')}' reported an error. "
                        f"Excerpt: {c.get('excerpt', '')[:200]}"
                    ),
                    severity="high",
                    session_id=None,
                )
            )

    return CollectionResult(
        episodes=episodes,
        session_count=len(digests),
        cron_errors=cron_errors,
    )


def _clean_turn(text: str) -> str:
    # Strip the system-injected reply-quote prefix Hermes adds.
    text = re.sub(r"^\[Replying to:.*?\]\s*", "", text, flags=re.DOTALL)
    return text.strip()


def _coerce_ts(started: Any) -> str:
    if started is None:
        return datetime.now(timezone.utc).isoformat()
    try:
        return datetime.fromtimestamp(float(started), timezone.utc).isoformat()
    except (TypeError, ValueError):
        return str(started)
