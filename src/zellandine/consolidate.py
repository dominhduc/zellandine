"""Stage 2 — Consolidate (NREM / Declarative Memory)

Convert collected episodes into structured proposals for memory,
skill, and user profile changes.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Literal

from .collect import CollectionResult

logger = logging.getLogger("zellandine")


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


_VALID_TARGETS = {"memory", "user", "skill"}
_VALID_ACTIONS = {"add", "replace", "remove", "patch", "create", "edit"}
_VALID_RISK = {"low", "medium", "high"}
_VALID_PRIORITY = {"low", "normal", "high"}


def consolidate(
    collected: CollectionResult,
    *,
    provider: Any = None,
    current_memory: str = "",
    current_user_profile: str = "",
    skill_list: str = "",
    existing_entries: list[str] | None = None,
    max_proposals: int = 5,
    min_confidence: float = 0.7,
    allow_soul_changes: bool = False,
    model: str | None = None,
) -> ConsolidationResult:
    """Consolidate collected episodes into structured proposals (Stage 2).

    Single provider pass: episodes + current state → JSON proposals, which are
    parsed, validated, guard-railed, and clamped to max_proposals.
    """
    if provider is None:
        from .providers import OfflineMarkerProvider

        provider = OfflineMarkerProvider()

    if not collected.episodes:
        return ConsolidationResult(model_used=getattr(provider, "name", ""))

    context = {
        "memory": current_memory,
        "user": current_user_profile,
        "skills": skill_list,
    }
    provider_name = getattr(provider, "name", "")
    try:
        raw = provider.consolidate(collected.to_prompt_block(), context)
    except Exception as exc:
        # Unattended nightly job: a transient LLM/provider failure must not
        # crash the whole cycle. Degrade to zero proposals, surface the error.
        logger.warning("consolidation provider failed: %s", exc)
        return ConsolidationResult(model_used=f"{provider_name} (error: {exc})")
    parsed = _parse_json_array(raw)

    existing_entries = existing_entries or []
    proposals: list[Proposal] = []
    for i, item in enumerate(parsed, 1):
        p = _to_proposal(item, fallback_id=f"dream-{i:03d}")
        if p is None:
            continue
        if not _passes_guards(p, min_confidence, allow_soul_changes):
            continue
        # Drop add-proposals that merely restate something already remembered.
        # (replace/remove/patch explicitly target existing entries, so skip them.)
        if p.action == "add" and _is_duplicate(p.content, existing_entries):
            continue
        proposals.append(p)

    # Highest-confidence first, then clamp.
    proposals.sort(key=lambda p: p.confidence, reverse=True)
    proposals = proposals[:max_proposals]

    return ConsolidationResult(
        proposals=proposals,
        model_used=getattr(provider, "name", ""),
    )


def _significant_words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-zA-Z0-9]{4,}", text.lower())}


def _is_duplicate(content: str, existing_entries: list[str], threshold: float = 0.7) -> bool:
    """True if `content` mostly restates an existing entry.

    Uses containment: the fraction of the proposal's significant words that
    already appear in a single existing entry. High containment ⇒ the proposal
    adds little new information.
    """
    words = _significant_words(content)
    if not words:
        return False
    for entry in existing_entries:
        ewords = _significant_words(entry)
        if not ewords:
            continue
        containment = len(words & ewords) / len(words)
        if containment >= threshold:
            return True
    return False


def _passes_guards(p: Proposal, min_confidence: float, allow_soul_changes: bool) -> bool:
    if p.confidence < min_confidence:
        return False
    # Never touch persona/SOUL unless explicitly allowed.
    if not allow_soul_changes and "soul" in (p.content + (p.skill_name or "")).lower():
        if "soul.md" in p.content.lower() or (p.skill_name or "").lower() == "soul":
            return False
    # Never delete skills; only patch/create/edit.
    if p.target == "skill" and p.action in ("remove",):
        return False
    # Memory removals require high confidence.
    if p.action == "remove" and p.confidence < 0.8:
        return False
    return True


def _to_proposal(item: dict[str, Any], *, fallback_id: str) -> Proposal | None:
    if not isinstance(item, dict):
        return None
    target = str(item.get("target", "")).lower().strip()
    action = str(item.get("action", "")).lower().strip()
    content = str(item.get("content", "")).strip()
    if target not in _VALID_TARGETS or action not in _VALID_ACTIONS:
        return None
    if not content and action not in ("remove",):
        return None
    # Reject proposals that would fail or no-op at apply time.
    target_entry = item.get("target_entry") or None
    old_string = item.get("old_string") if item.get("old_string") is not None else None
    new_string = item.get("new_string") if item.get("new_string") is not None else None
    skill_name = item.get("skill_name") or None
    if action in ("replace", "remove") and not target_entry:
        # Memory replace/remove need an existing entry to match against.
        return None
    if target == "skill" and action == "patch" and not (
        skill_name and old_string and new_string
    ):
        return None
    try:
        confidence = max(0.0, min(1.0, float(item.get("confidence", 0.0))))
    except (TypeError, ValueError):
        confidence = 0.0
    risk = str(item.get("risk", "low")).lower().strip()
    priority = str(item.get("priority", "normal")).lower().strip()
    return Proposal(
        id=str(item.get("id") or fallback_id),
        target=target,  # type: ignore[arg-type]
        action=action,  # type: ignore[arg-type]
        content=content,
        reason=str(item.get("reason", "")).strip(),
        confidence=confidence,
        risk=risk if risk in _VALID_RISK else "low",  # type: ignore[arg-type]
        priority=priority if priority in _VALID_PRIORITY else "normal",  # type: ignore[arg-type]
        provenance=str(item.get("provenance", "")).strip(),
        skill_name=skill_name,
        old_string=old_string,
        new_string=new_string,
        target_entry=target_entry,
    )


def _parse_json_array(text: str) -> list[dict[str, Any]]:
    """Best-effort extraction of a JSON array from an LLM response."""
    if not text:
        return []
    text = text.strip()
    # Strip markdown code fences if present.
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text).strip()
    try:
        data = json.loads(text)
    except Exception:
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if not match:
            return []
        try:
            data = json.loads(match.group(0))
        except Exception:
            return []
    if isinstance(data, dict):
        # Some models wrap the array, e.g. {"proposals": [...]}.
        for key in ("proposals", "items", "data"):
            if isinstance(data.get(key), list):
                return data[key]
        return [data]
    return data if isinstance(data, list) else []
