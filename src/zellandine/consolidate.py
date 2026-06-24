"""Stage 2 — Consolidate (NREM / Declarative Memory)

Convert collected episodes into structured proposals for memory,
skill, and user profile changes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from .collect import CollectionResult


ProposalAction = Literal["add", "replace", "remove", "patch", "create", "edit"]
ProposalTarget = Literal["memory", "user", "skill"]
ProposalRisk = Literal["low", "medium", "high"]
ProposalPriority = Literal["low", "normal", "high"]


@dataclass(slots=True, eq=True)
class Proposal:
    """A single staged change to Hermes state."""

    id: str
    target: ProposalTarget
    action: ProposalAction
    content: str
    reason: str
    confidence: float  # 0.0 – 1.0
    risk: ProposalRisk = "low"
    priority: ProposalPriority = "normal"
    provenance: str = ""
    approved: bool = False
    # For skill proposals
    skill_name: str | None = None
    old_string: str | None = None
    new_string: str | None = None
    # For memory replace/remove
    target_entry: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "id": self.id,
            "target": self.target,
            "action": self.action,
            "content": self.content,
            "reason": self.reason,
            "confidence": self.confidence,
            "risk": self.risk,
            "priority": self.priority,
            "provenance": self.provenance,
            "approved": self.approved,
        }
        if self.skill_name:
            d["skill_name"] = self.skill_name
        if self.old_string is not None:
            d["old_string"] = self.old_string
        if self.new_string is not None:
            d["new_string"] = self.new_string
        if self.target_entry:
            d["target_entry"] = self.target_entry
        return d

    @property
    def is_auto_applicable(self) -> bool:
        """Whether this proposal qualifies for auto-apply mode."""
        return self.confidence >= 0.9 and self.risk == "low"


@dataclass
class ConsolidationResult:
    """Output of Stage 2 — proposals ready for review."""

    proposals: list[Proposal] = field(default_factory=list)
    consolidated_at: str = ""
    model_used: str = ""
    tokens_consumed: int = 0

    def __post_init__(self) -> None:
        from datetime import datetime, timezone
        if not self.consolidated_at:
            self.consolidated_at = datetime.now(timezone.utc).isoformat()


def consolidate(
    collected: CollectionResult,
    *,
    current_memory: str = "",
    current_user_profile: str = "",
    skill_list: str = "",
    max_proposals: int = 5,
    model: str | None = None,
) -> ConsolidationResult:
    """Consolidate collected episodes into structured proposals.

    Single LLM pass: receives episodes + current state → outputs proposals.

    The prompt instructs the model to:
    1. Identify corrections/preferences that should be remembered
    2. Spot skill gaps or pitfalls discovered during sessions
    3. Flag outdated memory entries
    4. Cap output at max_proposals

    Returns a ConsolidationResult with staged proposals.
    """
    # TODO: Implement in Phase 1
    # - Build consolidation prompt from templates/consolidation_prompt.txt
    # - Call LLM via provider abstraction
    # - Parse structured JSON output into Proposal objects
    # - Validate proposals (target, action, confidence ranges)
    return ConsolidationResult()
