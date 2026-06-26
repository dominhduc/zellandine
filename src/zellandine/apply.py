"""Apply and revert staged proposals against live Hermes state.

This is the ONLY module that mutates Alfred's memory/skills, and only when
invoked explicitly via `zellandine apply`. Before applying, the current
memory files are snapshotted into the artifact's backup/ dir so the whole
operation is revertable.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import hermes_api
from .artifact import read_manifest, read_proposals


def _audit(path: Path, entry: dict[str, Any]) -> None:
    entry = {"ts": datetime.now(timezone.utc).isoformat(), **entry}
    with open(path / "audit.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _should_apply(p: dict[str, Any], *, auto: bool, auto_threshold: float,
                  priority: str | None, target_kind: str | None) -> bool:
    if priority and p.get("priority") != priority:
        return False
    if target_kind and p.get("target") != target_kind:
        return False
    if auto:
        return (
            float(p.get("confidence", 0)) >= auto_threshold
            and p.get("risk") == "low"
        )
    # Manual mode: apply proposals explicitly marked approved.
    return bool(p.get("approved"))


def apply_artifact(
    artifact_path: Path,
    *,
    auto: bool = False,
    auto_threshold: float = 0.9,
    dry_run: bool = False,
    priority: str | None = None,
    target_kind: str | None = None,
) -> dict[str, Any]:
    """Apply selected proposals from an artifact through native Hermes APIs."""
    manifest = read_manifest(artifact_path)
    proposals = read_proposals(artifact_path)

    selected = [
        p for p in proposals
        if _should_apply(p, auto=auto, auto_threshold=auto_threshold,
                         priority=priority, target_kind=target_kind)
    ]

    if not selected:
        return {"applied": 0, "skipped": len(proposals), "results": [],
                "note": "No proposals matched (mark approved, or use --auto)."}

    if dry_run:
        return {
            "applied": 0,
            "would_apply": len(selected),
            "results": [{"id": p.get("id"), "target": p.get("target"),
                         "action": p.get("action"), "preview": True} for p in selected],
        }

    # Snapshot memory before any mutation.
    backup = artifact_path / "backup"
    snapped = hermes_api.snapshot_memory(backup)
    _audit(artifact_path, {"event": "backup", "files": snapped})

    results: list[dict[str, Any]] = []
    applied = 0
    for p in selected:
        try:
            res = _apply_one(p)
            # Native MemoryStore/skill_manage signal failure via {"success": False}
            # rather than raising — a no-match replace/remove or limit overflow.
            ok = not (isinstance(res, dict) and res.get("success") is False)
            if ok:
                applied += 1
            results.append({"id": p.get("id"), "ok": ok, "result": res})
            _audit(artifact_path, {"event": "apply", "id": p.get("id"),
                                   "target": p.get("target"), "action": p.get("action"),
                                   "ok": ok})
        except Exception as exc:
            results.append({"id": p.get("id"), "ok": False, "error": str(exc)})
            _audit(artifact_path, {"event": "apply", "id": p.get("id"),
                                   "ok": False, "error": str(exc)})

    # Update manifest. Only declare "applied" if something actually changed.
    manifest.applied_count = applied
    if applied > 0:
        manifest.status = "applied"
    (artifact_path / "manifest.json").write_text(manifest.to_json(), encoding="utf-8")

    return {"applied": applied, "selected": len(selected), "results": results}


def _apply_one(p: dict[str, Any]) -> Any:
    target = p.get("target")
    action = p.get("action")
    if target in ("memory", "user"):
        return hermes_api.apply_memory(
            action=action,
            target=target,
            content=p.get("content", ""),
            old_text=p.get("target_entry"),
        )
    if target == "skill":
        if action != "patch":
            raise ValueError(f"only skill patch is supported via apply (got {action})")
        return hermes_api.apply_skill_patch(
            skill_name=p.get("skill_name") or "",
            old_string=p.get("old_string") or "",
            new_string=p.get("new_string") or "",
        )
    raise ValueError(f"unknown target: {target}")


def revert_artifact(artifact_path: Path) -> dict[str, Any]:
    """Restore memory from the artifact's backup snapshot.

    Note: skill patches are not auto-reverted (Hermes skill_manage has its own
    .bak files); memory is restored from snapshot.
    """
    backup = artifact_path / "backup"
    restored = hermes_api.restore_memory(backup)
    _audit(artifact_path, {"event": "revert", "restored": restored})

    try:
        manifest = read_manifest(artifact_path)
        manifest.status = "reverted"
        manifest.reverted_count = manifest.applied_count
        (artifact_path / "manifest.json").write_text(manifest.to_json(), encoding="utf-8")
    except Exception:
        pass

    return {"restored": restored,
            "note": "Memory restored from snapshot. Skill patches (if any) "
                    "must be reverted via Hermes' own .bak files."}
