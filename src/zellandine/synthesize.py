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
    provider: Any = None,
    max_insights: int = 3,
    model: str | None = None,
) -> SynthesisResult:
    """REM synthesis pass — cross-session pattern detection (Stage 4).

    Second provider pass (higher temperature): episodes + proposals → insights.
    Insights are NOT committed to memory — they surface in the report only.
    """
    if provider is None:
        from .providers import OfflineMarkerProvider

        provider = OfflineMarkerProvider()

    if not collected.episodes:
        return SynthesisResult(model_used=getattr(provider, "name", ""))

    from .consolidate import _parse_json_array

    proposals_text = "\n".join(
        f"- [{p.target}/{p.action}] {p.content} (conf {p.confidence})" for p in proposals
    ) or "(none)"

    try:
        raw = provider.synthesize(collected.to_prompt_block(), proposals_text)
    except Exception as exc:
        # REM synthesis is best-effort — never crash the cycle over it.
        import logging

        logging.getLogger("zellandine").warning("synthesis provider failed: %s", exc)
        return SynthesisResult(model_used=f"{getattr(provider, 'name', '')} (error: {exc})")
    parsed = _parse_json_array(raw)

    insights: list[Insight] = []
    valid_types = {"pattern", "connection", "suggestion", "drift_alert"}
    for item in parsed:
        if not isinstance(item, dict):
            continue
        itype = str(item.get("type", "pattern")).lower().strip()
        content = str(item.get("content", "")).strip()
        if not content:
            continue
        try:
            conf = max(0.0, min(1.0, float(item.get("confidence", 0.5))))
        except (TypeError, ValueError):
            conf = 0.5
        insights.append(
            Insight(
                type=itype if itype in valid_types else "pattern",
                content=content,
                evidence=str(item.get("evidence", "")).strip(),
                confidence=conf,
            )
        )

    return SynthesisResult(
        insights=insights[:max_insights],
        model_used=getattr(provider, "name", ""),
    )
