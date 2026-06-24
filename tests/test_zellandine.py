"""Tests for Zellandine dream cycle."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


class TestScoring:
    """Stage 3 — importance scoring."""

    def test_fresh_critical_entry_scores_high(self):
        from zellandine.prune import score_entry

        result = score_entry("⚠️ NEVER greet without checking clock", age_days=1, correction_count=5)
        assert result.score > 0.3
        assert result.recommendation == "keep"

    def test_old_unused_entry_flags_archive(self):
        from zellandine.prune import score_entry

        result = score_entry("Temporary config note", age_days=200, correction_count=0)
        assert result.recommendation == "archive"

    def test_very_old_unused_entry_flags_remove(self):
        from zellandine.prune import score_entry

        result = score_entry("Stale reference", age_days=365, correction_count=0)
        assert result.recommendation == "remove"

    def test_referenced_entry_survives_age(self):
        from zellandine.prune import score_entry

        result = score_entry("Important path", age_days=200, correction_count=8)
        assert result.recommendation == "keep"

    def test_recency_factor_never_below_floor(self):
        from zellandine.prune import score_entry

        result = score_entry("Old entry", age_days=9999, correction_count=0)
        assert result.recency_factor == 0.1  # floor


class TestArtifact:
    """Artifact read/write."""

    def test_manifest_creation(self, tmp_path):
        from zellandine.artifact import Manifest

        m = Manifest(artifact_id="dream-2026-06-24")
        assert m.status == "staged"
        assert m.artifact_id == "dream-2026-06-24"
        assert "dream" in m.created_at or "2026" in m.created_at

    def test_write_and_read_manifest(self, tmp_path):
        from zellandine.artifact import Manifest, write_artifact, read_manifest

        manifest = Manifest(artifact_id="dream-test", proposal_count=3)
        write_artifact(tmp_path / "dream-test", manifest, [], "test report")
        loaded = read_manifest(tmp_path / "dream-test")
        assert loaded.artifact_id == "dream-test"
        assert loaded.proposal_count == 3

    def test_find_latest_artifact(self, tmp_path):
        from zellandine.artifact import Manifest, write_artifact, find_latest_artifact

        root = tmp_path / "artifacts"
        for i, name in enumerate(["dream-2026-06-01", "dream-2026-06-02", "dream-2026-06-03"]):
            m = Manifest(artifact_id=name)
            path = root / name
            write_artifact(path, m, [], f"report {i}")
        latest = find_latest_artifact(root)
        assert latest is not None
        assert "dream-2026-06-03" in str(latest) or "dream" in str(latest)

    def test_find_latest_returns_none_on_empty(self, tmp_path):
        from zellandine.artifact import find_latest_artifact

        assert find_latest_artifact(tmp_path / "nonexistent") is None


class TestOfflineProvider:
    """Offline marker provider."""

    def test_extracts_dream_markers(self):
        from zellandine.providers import OfflineMarkerProvider

        provider = OfflineMarkerProvider()
        text = """
        DREAM: memory: Always check timezone before greeting
        DREAM: user: Prefers British English spelling
        Some other text
        DREAM: skill: path=skills/review.md | Update checklist
        """
        result = provider.consolidate(text, "")
        proposals = json.loads(result)
        assert len(proposals) == 3
        assert proposals[0]["target"] == "memory"
        assert proposals[1]["target"] == "user"

    def test_no_markers_returns_empty(self):
        from zellandine.providers import OfflineMarkerProvider

        provider = OfflineMarkerProvider()
        result = provider.consolidate("Nothing here", "")
        proposals = json.loads(result)
        assert len(proposals) == 0

    def test_synthesize_returns_empty(self):
        from zellandine.providers import OfflineMarkerProvider

        provider = OfflineMarkerProvider()
        result = provider.synthesize("episodes", "proposals")
        insights = json.loads(result)
        assert len(insights) == 0


class TestState:
    """Dream cycle state."""

    def test_default_state(self, tmp_path, monkeypatch):
        from zellandine import state

        monkeypatch.setattr("zellandine.state.get_hermes_home", lambda: tmp_path)
        monkeypatch.setattr("zellandine.state.state_path", lambda: tmp_path / "zellandine" / "state.json")

        s = state.read_state()
        assert s["last_dream_at"] is None
        assert s["total_cycles"] == 0

    def test_record_cycle_updates_state(self, tmp_path, monkeypatch):
        from zellandine import state

        monkeypatch.setattr("zellandine.state.state_path", lambda: tmp_path / "state.json")

        state.record_cycle(
            artifact_id="dream-test",
            episode_count=5,
            proposal_count=2,
            applied_count=1,
        )
        s = state.read_state()
        assert s["total_cycles"] == 1
        assert s["total_proposals"] == 2
        assert s["total_applied"] == 1
        assert s["last_dream_at"] is not None


class TestReport:
    """Stage 5 — report generation."""

    def test_empty_report(self):
        from zellandine.report import generate_report

        report = generate_report(
            artifact_id="dream-test",
            episode_count=0,
            proposals=[],
        )
        assert "Dream Report" in report
        assert "Episodes collected:** 0" in report

    def test_report_with_proposals(self):
        from zellandine.report import generate_report
        from zellandine.consolidate import Proposal

        proposals = [
            Proposal(
                id="dream-001",
                target="memory",
                action="add",
                content="Check timezone before greeting",
                reason="User corrected this 3 times",
                confidence=0.95,
            ),
        ]
        report = generate_report(
            artifact_id="dream-test",
            episode_count=5,
            proposals=proposals,
        )
        assert "Memory Proposals" in report
        assert "Check timezone" in report

    def test_telegram_digest_short(self):
        from zellandine.report import generate_telegram_digest
        from zellandine.consolidate import Proposal

        digest = generate_telegram_digest(
            artifact_id="dream-test",
            episode_count=10,
            proposals=[
                Proposal(
                    id="dream-001",
                    target="memory",
                    action="add",
                    content="Prefers concise responses",
                    reason="Multiple corrections",
                    confidence=0.95,
                    priority="high",
                ),
            ],
        )
        assert "🌙" in digest
        assert "Notable proposals" in digest
        assert "Prefers concise" in digest
