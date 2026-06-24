"""Stage 5 — Report (Wake / Dream Journal)

Generate the dream report, write artifacts, deliver summaries.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .consolidate import Proposal
from .synthesize import SynthesisResult


def generate_report(
    *,
    artifact_id: str,
    episode_count: int,
    proposals: list[Proposal],
    synthesis: SynthesisResult | None = None,
    dry_run: bool = False,
) -> str:
    """Generate the full dream report in Markdown.

    This is written to artifacts/<id>/report.md and also used
    as the Telegram digest source.
    """
    lines = [
        f"# Dream Report — {artifact_id}",
        "",
        f"_Generated at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}_",
        "",
    ]

    if dry_run:
        lines.append("> ⚠️ **Dry run** — no changes staged or applied.")
        lines.append("")

    # Summary stats
    lines.extend([
        "## Summary",
        "",
        f"- **Episodes collected:** {episode_count}",
        f"- **Proposals staged:** {len(proposals)}",
        f"- **High confidence:** {sum(1 for p in proposals if p.confidence >= 0.9)}",
        f"- **Medium confidence:** {sum(1 for p in proposals if 0.7 <= p.confidence < 0.9)}",
        f"- **Low confidence:** {sum(1 for p in proposals if p.confidence < 0.7)}",
        "",
    ])

    # Proposals by target
    for target in ("memory", "user", "skill"):
        target_props = [p for p in proposals if p.target == target]
        if not target_props:
            continue
        lines.extend([
            f"## {target.title()} Proposals ({len(target_props)})",
            "",
        ])
        for p in target_props:
            status = "✅" if p.approved else "⬜"
            lines.append(f"### {status} {p.id} — {p.action}")
            lines.append(f"**Confidence:** {p.confidence} | **Risk:** {p.risk} | **Priority:** {p.priority}")
            lines.append(f"**Reason:** {p.reason}")
            lines.append(f"**Content:** {p.content}")
            if p.provenance:
                lines.append(f"_Provenance: {p.provenance}_")
            lines.append("")

    # Synthesis (REM)
    if synthesis and synthesis.insights:
        lines.append(synthesis.to_markdown())
        lines.append("")

    # Footer
    lines.extend([
        "---",
        "",
        f"_Zellandine v0.1.0 — _La Belle au Bois Dormant_",
    ])

    return "\n".join(lines)


def generate_telegram_digest(
    *,
    artifact_id: str,
    episode_count: int,
    proposals: list[Proposal],
    synthesis: SynthesisResult | None = None,
) -> str:
    """Generate a concise Telegram-friendly digest.

    This is what gets delivered to the user's chat after each dream cycle.
    Kept short — just the highlights.
    """
    lines = [
        f"🌙 **Dream Report — {artifact_id}**",
        "",
        f"Scanned {episode_count} episodes. Staged {len(proposals)} proposals.",
        "",
    ]

    # Only surface high-priority or high-confidence items
    notable = [p for p in proposals if p.priority == "high" or p.confidence >= 0.9]
    if notable:
        lines.append("**Notable proposals:**")
        for p in notable[:5]:
            lines.append(f"• `{p.target}/{p.action}` — {p.content[:80]}")
        lines.append("")

    if synthesis and synthesis.insights:
        lines.append("**Insights:**")
        for i in synthesis.insights[:3]:
            lines.append(f"• {i.content[:100]}")
        lines.append("")

    # Count by status
    approved = sum(1 for p in proposals if p.approved)
    if approved:
        lines.append(f"_{approved} proposals approved, ready to apply._")
    else:
        lines.append("_Review with `zellandine review` to approve._")

    return "\n".join(lines)
