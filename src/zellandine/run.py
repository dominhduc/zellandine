"""Dream cycle orchestrator.

Wires the five stages into one run, writes an artifact, and returns a
summary. This is the function the CLI `run` command and the cron script call.

The run NEVER mutates live Hermes state — it only stages proposals and
produces a report/digest. Mutation happens in a separate `apply` step.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from . import hermes_api, state
from .artifact import Manifest, artifact_dir, write_artifact
from .collect import collect
from .config import Config, build_provider, load_config
from .consolidate import consolidate
from .report import generate_report, generate_telegram_digest
from .synthesize import synthesize


def default_artifact_root() -> Path:
    return Path(hermes_api.hermes_home()) / "zellandine" / "artifacts"


def run_cycle(
    *,
    config: Config | None = None,
    depth: str = "full",
    dry_run: bool = False,
    session_limit: int | None = None,
    artifact_root: Path | None = None,
    time_budget_s: float | None = None,
    clock: Callable[[], float] | None = None,
) -> dict[str, Any]:
    """Run a full dream cycle. Returns a summary dict (incl. artifact path).

    `time_budget_s` guards the optional REM synthesis: if consolidation already
    consumed more than this, synthesis is skipped so the whole cycle finishes
    inside Hermes' cron script limit. `clock` is injectable for testing.
    """
    cfg = config or load_config()
    depth = depth or cfg.depth
    session_limit = session_limit or cfg.session_lookback
    artifact_root = artifact_root or default_artifact_root()
    provider = build_provider(cfg)
    if time_budget_s is None:
        time_budget_s = cfg.time_budget_s
    clock = clock or time.monotonic
    started_at_mono = clock()

    audit: list[dict[str, Any]] = []

    def log(stage: str, **data: Any) -> None:
        audit.append(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "stage": stage,
                **data,
            }
        )

    # Stage 1 — Collect
    collected = collect(session_limit=session_limit)
    log("collect", episodes=len(collected.episodes), sessions=collected.session_count,
        cron_errors=len(collected.cron_errors))

    # Stage 2 — Consolidate
    mem = hermes_api.memory_context_block()
    raw_memory = hermes_api.read_memory()
    consolidation = consolidate(
        collected,
        provider=provider,
        current_memory=mem["memory"],
        current_user_profile=mem["user"],
        skill_list=hermes_api.skill_context_block(),
        existing_entries=raw_memory.get("memory", []) + raw_memory.get("user", []),
        max_proposals=cfg.max_proposals,
        min_confidence=cfg.min_confidence,
        allow_soul_changes=cfg.allow_soul_changes,
    )
    proposals = consolidation.proposals
    log("consolidate", proposals=len(proposals), provider=consolidation.model_used)

    # Stage 3 — Prune (duplicate detection); part of the "full" cycle only.
    if depth == "full":
        from .prune import find_duplicate_entries

        dup_proposals = find_duplicate_entries(
            raw_memory.get("memory", []) + raw_memory.get("user", [])
        )
        log("prune", duplicates=len(dup_proposals))
        # Combine, honouring the max_proposals guard rail (consolidation first).
        proposals = (proposals + dup_proposals)[: cfg.max_proposals]

    # Stage 4 — Synthesize (REM); skipped in "light" depth, and skipped under
    # time pressure (it's best-effort and never committed to memory).
    synthesis = None
    synthesis_skipped = False
    if depth == "full":
        elapsed = clock() - started_at_mono
        if elapsed > time_budget_s:
            synthesis_skipped = True
            log("synthesize", skipped=True, elapsed=round(elapsed, 1))
        else:
            synthesis = synthesize(collected, proposals, provider=provider)
            log("synthesize", insights=len(synthesis.insights))

    # Stage 5 — Report
    artifact_id = f"dream-{datetime.now(timezone.utc).strftime('%Y-%m-%d')}"
    report = generate_report(
        artifact_id=artifact_id,
        episode_count=len(collected.episodes),
        proposals=proposals,
        synthesis=synthesis,
        dry_run=dry_run,
    )
    digest = generate_telegram_digest(
        artifact_id=artifact_id,
        episode_count=len(collected.episodes),
        proposals=proposals,
        synthesis=synthesis,
    )

    manifest = Manifest(
        artifact_id=artifact_id,
        status="dry-run" if dry_run else "staged",
        depth=depth,
        dry_run=dry_run,
        session_count=collected.session_count,
        episode_count=len(collected.episodes),
        proposal_count=len(proposals),
        config={
            "apply_mode": cfg.apply_mode,
            "max_proposals": cfg.max_proposals,
            "min_confidence": cfg.min_confidence,
            "provider": consolidation.model_used,
            "session_lookback": session_limit,
        },
    )

    path = None
    if not dry_run:
        path = artifact_dir(artifact_root, artifact_id)
        log("report", artifact=str(path))
        write_artifact(path, manifest, proposals, report, audit_entries=audit)
        state.record_cycle(
            artifact_id=artifact_id,
            episode_count=len(collected.episodes),
            proposal_count=len(proposals),
            session_ids=[d for d in (e.session_id for e in collected.episodes) if d],
        )

    return {
        "artifact_id": artifact_id,
        "artifact_path": str(path) if path else None,
        "dry_run": dry_run,
        "episode_count": len(collected.episodes),
        "session_count": collected.session_count,
        "proposal_count": len(proposals),
        "insight_count": len(synthesis.insights) if synthesis else 0,
        "synthesis_skipped": synthesis_skipped,
        "provider": consolidation.model_used,
        "report": report,
        "digest": digest,
    }
