"""Stage 4 — Synthesize (REM / Associative Memory)

Cross-reference sessions, surface patterns, generate novel insights.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .collect import CollectionResult
from .consolidate import Proposal


@dataclass
class Insight:
    """A non-obvious pattern or connection surfaced during REM synthesis."""

    type: str  # pattern | connection | suggestion | drift_alert
    content: str
    evidence: str  # session IDs or timestamps that support this insight
    confidence: float = 0.5  # REM insights are inherently speculative

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "content": self.content,
            "evidence": self.evidence,
            "confidence": self.confidence,
        }


@dataclass
class SynthesisResult:
    """Output of Stage 4 — insights for the dream report."""

    insights: list[Insight] = field(default_factory=list)
    synthesized_at: str = ""
    model_used: str = ""
    tokens_consumed: int = 0

    def __post_init__(self) -> None:
        if not self.synthesized_at:
            self.synthesized_at = datetime.now(timezone.utc).isoformat()

    def to_markdown(self) -> str:
        """Render insights for the dream report."""
        if not self.insights:
            return "### Patterns & Insights\n\nNo patterns surfaced this cycle.\n"

        lines = ["### Patterns & Insights", ""]
        type_emoji = {
            "pattern": "🔗",
            "connection": "💡",
            "suggestion": "💭",
            "drift_alert": "⚠️",
        }
        for i, insight in enumerate(self.insights, 1):
            emoji = type_emoji.get(insight.type, "•")
            lines.append(
                f"{i}. {emoji} **[{insight.type}]** {insight.content}\n"
                f"   _Evidence: {insight.evidence}_"
            )
        return "\n".join(lines) + "\n"


def synthesize(
    collected: CollectionResult,
    proposals: list[Proposal],
    *,
    model: str | None = None,
) -> SynthesisResult:
    """REM synthesis pass — cross-session pattern detection.

    Second LLM pass (higher temperature): receives episodes + proposals
    and looks for:
    1. Recurring themes across sessions
    2. Non-obvious connections between episodes
    3. Behavioural drift from stated preferences
    4. 1-3 novel insights worth surfacing

    Insights are NOT committed to memory — they go in the report for human review.
    """
    # TODO: Implement in Phase 2
    return SynthesisResult()
