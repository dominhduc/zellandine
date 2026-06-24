"""Stage 1 — Collect (Sleep Onset / Hippocampal Replay)

Gather raw material from recent Hermes sessions and cron outputs.
"""
from __future__ import annotations

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


def collect(
    session_limit: int = 14,
    *,
    hermes_home: Path | None = None,
) -> CollectionResult:
    """Collect episodes from recent Hermes sessions and cron outputs.

    This is the main entry point for Stage 1. It:
    1. Reads recent sessions via the session database
    2. Reads cron output logs for errors/anomalies
    3. Extracts salient episodes

    Returns a CollectionResult ready for Stage 2 (consolidation).
    """
    # TODO: Implement in Phase 1
    # - Read session DB (hermes_state.SessionDB or direct SQLite)
    # - Scan cron outputs in ~/.hermes/cron/output/
    # - Extract user turns, corrections, decisions, errors
    # - Classify into episode types
    return CollectionResult()
