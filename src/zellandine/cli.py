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

    # Commands will be dispatched to handler modules
    # For now, each returns a helpful message
    print(f"[zellandine] Command '{args.command}' — not yet implemented.")
    print(f"[zellandine] This is a scaffold. Implementation coming in Phase 1.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
