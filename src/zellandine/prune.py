"""Stage 3 — Prune (Synaptic Downscaling)

Score memory entries, apply forgetting curves, flag duplicates
and stale knowledge for removal.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .consolidate import Proposal


@dataclass(slots=True)
class MemoryScore:
    """Importance score for a single memory entry."""

    entry_snippet: str
    score: float
    base_weight: float
    recency_factor: float
    reference_boost: float
    age_days: int
    recommendation: str  # keep | archive | remove

    @property
    def should_prune(self) -> bool:
        return self.recommendation in ("archive", "remove")


def score_entry(
    entry_text: str,
    *,
    age_days: int,
    correction_count: int = 0,
    is_critical: bool = False,
    half_life_days: int = 180,
) -> MemoryScore:
    """Score a memory entry using importance × recency × references.

    Formula (adapted from Auto-Dream):
        importance = (base_weight × recency_factor × reference_boost) / 8.0

    - base_weight: 1.0 default, 2.0 if critical (⚠️), 0.5 if soft preference
    - recency_factor: max(0.1, 1.0 - age_days / half_life_days)
    - reference_boost: log2(correction_count + 1)
    """
    base_weight = 2.0 if is_critical else 1.0
    recency_factor = max(0.1, 1.0 - age_days / half_life_days)
    # +2 offset ensures entries with 0 corrections still have non-zero scores
    reference_boost = math.log2(correction_count + 2)
    score = (base_weight * recency_factor * reference_boost) / 4.0

    if score < 0.03 and age_days > 300:
        recommendation = "remove"
    elif score < 0.05 and age_days > 90:
        recommendation = "archive"
    else:
        recommendation = "keep"

    return MemoryScore(
        entry_snippet=entry_text[:80] + ("..." if len(entry_text) > 80 else ""),
        score=round(score, 4),
        base_weight=base_weight,
        recency_factor=round(recency_factor, 4),
        reference_boost=round(reference_boost, 4),
        age_days=age_days,
        recommendation=recommendation,
    )


def prune(
    memory_entries: list[str],
    *,
    entry_ages: list[int] | None = None,
    correction_counts: list[int] | None = None,
    half_life_days: int = 180,
) -> list[Proposal]:
    """Prune memory entries by scoring and flagging low-value ones.

    Returns proposals (remove/archive) for entries that score below threshold.
    """
    if entry_ages is None:
        entry_ages = [0] * len(memory_entries)
    if correction_counts is None:
        correction_counts = [0] * len(memory_entries)

    proposals: list[Proposal] = []
    for i, (entry, age, refs) in enumerate(zip(memory_entries, entry_ages, correction_counts)):
        is_critical = "⚠️" in entry
        score = score_entry(
            entry,
            age_days=age,
            correction_count=refs,
            is_critical=is_critical,
            half_life_days=half_life_days,
        )
        if score.should_prune:
            proposals.append(
                Proposal(
                    id=f"prune-{i:03d}",
                    target="memory",
                    action="remove" if score.recommendation == "remove" else "replace",
                    content=f"[ARCHIVED] {entry}",
                    reason=f"Score {score.score} ({score.recommendation}): "
                    f"age={age}d, refs={refs}, recency={score.recency_factor}",
                    confidence=0.7,
                    risk="low",
                    priority="low",
                    target_entry=entry[:100],
                )
            )
    return proposals
