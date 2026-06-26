"""CLI entry point for Zellandine dream cycle."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="zellandine",
        description="Sleep-inspired memory consolidation for Hermes Agent.",
    )
    parser.add_argument("--version", action="version", version=f"zellandine {__version__}")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # run
    run_parser = subparsers.add_parser("run", help="Run a dream cycle")
    run_parser.add_argument(
        "--depth",
        choices=["full", "light"],
        default="full",
        help="Dream depth: full (all stages) or light (collect + consolidate only)",
    )
    run_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report only — no changes staged or applied",
    )
    run_parser.add_argument(
        "--sessions",
        type=int,
        default=14,
        help="Number of recent sessions to scan (default: 14)",
    )
    run_parser.add_argument(
        "--live-root",
        type=Path,
        default=None,
        help="Live state root (default: ~/.hermes)",
    )
    run_parser.add_argument(
        "--artifact-root",
        type=Path,
        default=None,
        help="Artifact output directory (default: ~/.hermes/zellandine/artifacts)",
    )

    # review
    review_parser = subparsers.add_parser("review", help="Review staged proposals")
    review_parser.add_argument(
        "artifact_id",
        nargs="?",
        help="Artifact ID to review (omit for latest)",
    )
    review_parser.add_argument("--latest", action="store_true", help="Open the most recent artifact")

    # apply
    apply_parser = subparsers.add_parser("apply", help="Apply approved proposals")
    apply_parser.add_argument("artifact_id", help="Artifact to apply")
    apply_parser.add_argument("--auto", action="store_true", help="Auto-approve high-confidence proposals")
    apply_parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    apply_parser.add_argument(
        "--priority",
        choices=["low", "normal", "high"],
        help="Filter proposals by priority",
    )
    apply_parser.add_argument(
        "--target-kind",
        choices=["memory", "user", "skill"],
        help="Filter proposals by target type",
    )

    # revert
    revert_parser = subparsers.add_parser("revert", help="Revert an applied artifact")
    revert_parser.add_argument("artifact_id", help="Artifact to revert")
    revert_parser.add_argument("--yes", action="store_true", help="Skip confirmation")

    # status
    subparsers.add_parser("status", help="Show dream cycle status")

    # install-cron
    cron_parser = subparsers.add_parser("install-cron", help="Install nightly dream cron job")
    cron_parser.add_argument(
        "--schedule",
        default="0 2 * * *",
        help="Cron schedule expression (default: 0 2 * * *)",
    )

    # digest
    digest_parser = subparsers.add_parser("digest", help="Render operator digest")
    digest_parser.add_argument("artifact_id", help="Artifact to digest")
    digest_parser.add_argument("--weekly", action="store_true", help="Include weekly rollup")

    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    handlers = {
        "run": _cmd_run,
        "review": _cmd_review,
        "apply": _cmd_apply,
        "revert": _cmd_revert,
        "status": _cmd_status,
        "install-cron": _cmd_install_cron,
        "digest": _cmd_digest,
    }
    handler = handlers.get(args.command)
    if handler is None:
        parser.print_help()
        return 1
    try:
        return handler(args)
    except Exception as exc:  # surface errors cleanly for cron logs
        print(f"[zellandine] error in '{args.command}': {exc}", file=sys.stderr)
        return 1


def _artifact_root(args) -> Path:
    from .run import default_artifact_root

    return getattr(args, "artifact_root", None) or default_artifact_root()


def _resolve_artifact(artifact_id: str | None, root: Path) -> Path | None:
    from .artifact import find_latest_artifact

    if not artifact_id or artifact_id == "--latest":
        return find_latest_artifact(root)
    p = root / artifact_id
    return p if p.exists() else None


def _cmd_run(args) -> int:
    from .config import load_config
    from .run import run_cycle

    cfg = load_config()
    summary = run_cycle(
        config=cfg,
        depth=args.depth,
        dry_run=args.dry_run,
        session_limit=args.sessions,
        artifact_root=getattr(args, "artifact_root", None),
    )
    print(f"🌙 Dream cycle complete — {summary['artifact_id']}")
    print(
        f"   sessions={summary['session_count']} episodes={summary['episode_count']} "
        f"proposals={summary['proposal_count']} insights={summary['insight_count']} "
        f"provider={summary['provider']}"
    )
    if summary["artifact_path"]:
        print(f"   artifact: {summary['artifact_path']}")
    else:
        print("   (dry-run — nothing written)")
    print()
    print(summary["digest"])
    return 0


def _cmd_review(args) -> int:
    root = _artifact_root(args)
    path = _resolve_artifact(args.artifact_id, root)
    if path is None:
        print("[zellandine] no artifact found.")
        return 1
    report = path / "report.md"
    if report.exists():
        print(report.read_text(encoding="utf-8"))
    else:
        print(f"[zellandine] artifact at {path} has no report.md")
    print(f"\n[zellandine] proposals: {path / 'proposals.jsonl'}")
    print("[zellandine] to apply: zellandine apply", path.name, "--auto  (or mark 'approved' in proposals.jsonl)")
    return 0


def _cmd_apply(args) -> int:
    from .apply import apply_artifact
    from .config import load_config

    cfg = load_config()
    root = _artifact_root(args)
    path = _resolve_artifact(args.artifact_id, root)
    if path is None:
        print("[zellandine] no artifact found.")
        return 1
    result = apply_artifact(
        path,
        auto=args.auto,
        auto_threshold=cfg.auto_apply_threshold,
        dry_run=args.dry_run,
        priority=args.priority,
        target_kind=args.target_kind,
    )
    print(f"[zellandine] apply {path.name}: {result}")
    return 0


def _cmd_revert(args) -> int:
    from .apply import revert_artifact

    root = _artifact_root(args)
    path = _resolve_artifact(args.artifact_id, root)
    if path is None:
        print("[zellandine] no artifact found.")
        return 1
    if not args.yes:
        print(f"[zellandine] this will restore memory from {path.name}/backup. Re-run with --yes.")
        return 1
    print(f"[zellandine] revert: {revert_artifact(path)}")
    return 0


def _cmd_status(args) -> int:
    from . import state
    from .artifact import find_latest_artifact

    s = state.read_state()
    print("🌙 Zellandine status")
    print(f"   last dream: {s.get('last_dream_at') or 'never'}")
    print(f"   total cycles: {s.get('total_cycles', 0)}")
    print(f"   total proposals: {s.get('total_proposals', 0)}")
    print(f"   total applied: {s.get('total_applied', 0)}")
    latest = find_latest_artifact(_artifact_root(args))
    print(f"   latest artifact: {latest.name if latest else 'none'}")
    return 0


def _cmd_install_cron(args) -> int:
    from . import hermes_api
    from .install import ensure_cron_script

    script_rel = ensure_cron_script()
    try:
        job = hermes_api.create_cron_job(
            name="Zellandine Dream Cycle",
            schedule=args.schedule,
            script=script_rel,
            deliver="telegram",
        )
        print(f"[zellandine] cron job registered: {job.get('id', job)}")
        print(f"   schedule: {args.schedule}  script: {script_rel}  (no_agent, delivers to telegram)")
    except Exception as exc:
        print(f"[zellandine] could not register cron job automatically: {exc}", file=sys.stderr)
        print(f"   The cycle script is installed at ~/.hermes/scripts/{script_rel}")
        print("   Register it manually via Hermes' cronjob tool (no_agent=true).")
        return 1
    return 0


def _cmd_digest(args) -> int:
    root = _artifact_root(args)
    path = _resolve_artifact(args.artifact_id, root)
    if path is None:
        print("[zellandine] no artifact found.")
        return 1
    from .artifact import read_manifest, read_proposals
    from .consolidate import Proposal
    from .report import generate_telegram_digest

    manifest = read_manifest(path)
    raw = read_proposals(path)
    proposals = [Proposal(**{k: v for k, v in p.items()
                             if k in Proposal.__dataclass_fields__}) for p in raw]
    print(generate_telegram_digest(
        artifact_id=manifest.artifact_id,
        episode_count=manifest.episode_count,
        proposals=proposals,
    ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
