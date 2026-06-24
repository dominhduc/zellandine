"""Artifact management — staged proposals, reports, and audit trails.

Each dream cycle writes a self-contained artifact directory:

    artifacts/dream-YYYY-MM-DD/
      manifest.json     — run metadata, timestamps, config
      report.md         — human-readable dream report
      proposals.jsonl   — one JSON object per proposal
      audit.jsonl       — every action, timestamped
      backup/           — pre-apply memory/skill snapshots
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .consolidate import Proposal


@dataclass
class Manifest:
    """Artifact metadata — describes a single dream cycle run."""

    artifact_id: str
    created_at: str = ""
    status: str = "staged"  # staged → reviewed → approved → applied → reverted
    depth: str = "full"  # full | light
    dry_run: bool = False
    session_count: int = 0
    episode_count: int = 0
    proposal_count: int = 0
    applied_count: int = 0
    reverted_count: int = 0
    config: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()
        if not self.artifact_id:
            self.artifact_id = f"dream-{datetime.now(timezone.utc).strftime('%Y-%m-%d')}"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False, default=str)


def artifact_dir(artifact_root: Path, artifact_id: str | None = None) -> Path:
    """Get or create the artifact directory for a given ID."""
    if artifact_id is None:
        artifact_id = f"dream-{datetime.now(timezone.utc).strftime('%Y-%m-%d')}"
    path = artifact_root / artifact_id
    path.mkdir(parents=True, exist_ok=True)
    (path / "backup").mkdir(exist_ok=True)
    return path


def write_artifact(
    path: Path,
    manifest: Manifest,
    proposals: list[Proposal],
    report: str,
    audit_entries: list[dict[str, Any]] | None = None,
) -> Path:
    """Write a complete artifact to disk.

    Returns the artifact directory path.
    """
    path.mkdir(parents=True, exist_ok=True)
    (path / "backup").mkdir(exist_ok=True)

    # Manifest
    (path / "manifest.json").write_text(manifest.to_json(), encoding="utf-8")

    # Proposals
    with open(path / "proposals.jsonl", "w", encoding="utf-8") as f:
        for p in proposals:
            f.write(json.dumps(p.to_dict(), ensure_ascii=False) + "\n")

    # Report
    (path / "report.md").write_text(report, encoding="utf-8")

    # Audit log
    with open(path / "audit.jsonl", "a", encoding="utf-8") as f:
        for entry in audit_entries or []:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    return path


def read_manifest(path: Path) -> Manifest:
    """Read a manifest from an artifact directory."""
    data = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    return Manifest(**data)


def read_proposals(path: Path) -> list[dict[str, Any]]:
    """Read proposals from an artifact directory."""
    proposals_file = path / "proposals.jsonl"
    if not proposals_file.exists():
        return []
    proposals = []
    for line in proposals_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            proposals.append(json.loads(line))
    return proposals


def find_latest_artifact(artifact_root: Path) -> Path | None:
    """Find the most recent artifact directory."""
    if not artifact_root.exists():
        return None
    dirs = sorted(
        [d for d in artifact_root.iterdir() if d.is_dir() and (d / "manifest.json").exists()],
        key=lambda d: (d / "manifest.json").stat().st_mtime,
        reverse=True,
    )
    return dirs[0] if dirs else None
