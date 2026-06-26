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


class TestPruneDuplicates:
    """Stage 3 — metadata-free duplicate detection over memory entries."""

    def test_flags_near_identical_entries(self):
        from zellandine.prune import find_duplicate_entries

        entries = [
            "User prefers concise British English replies.",
            "User likes concise replies in British English.",
            "User is based in Hanoi, Vietnam, GMT+7 timezone.",
        ]
        props = find_duplicate_entries(entries)
        assert len(props) >= 1
        assert all(p.target == "memory" for p in props)
        # Proposals must carry a target_entry so they're applyable/valid.
        assert all(p.target_entry for p in props)
        # Consolidation means REMOVING the redundant entry (not replacing it with
        # a copy of the one we keep — that would create two identical entries).
        assert all(p.action == "remove" for p in props)

    def test_no_duplicates_when_distinct(self):
        from zellandine.prune import find_duplicate_entries

        entries = ["Likes cats.", "Works at SmartOSC.", "Based in Hanoi."]
        assert find_duplicate_entries(entries) == []

    def test_low_priority_and_not_auto_applicable(self):
        from zellandine.prune import find_duplicate_entries

        entries = [
            "User prefers concise British English replies.",
            "User likes concise replies in British English.",
        ]
        props = find_duplicate_entries(entries)
        assert props and props[0].priority == "low"
        # Duplicate-merge suggestions must never auto-apply.
        assert not props[0].is_auto_applicable


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

    def test_report_footer_well_formed(self):
        from zellandine.report import generate_report

        report = generate_report(artifact_id="dream-test", episode_count=0, proposals=[])
        # The old footer had a malformed double-italic: "— _La Belle ... _".
        assert "— _La Belle" not in report
        assert "La Belle au Bois Dormant" in report

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


class TestCollectClassify:
    """Stage 1 — episode classification heuristics."""

    def test_correction_detected(self):
        from zellandine.collect import _classify

        etype, severity = _classify("No, never greet me with assumed time of day")
        assert etype == "correction"
        assert severity == "high"

    def test_preference_detected(self):
        from zellandine.collect import _classify

        etype, _ = _classify("I prefer concise British English replies")
        assert etype == "preference"

    def test_plain_text_is_info(self):
        from zellandine.collect import _classify

        etype, severity = _classify("here is a screenshot")
        assert etype == "info"
        assert severity == "low"

    def test_reply_prefix_stripped(self):
        from zellandine.collect import _clean_turn

        cleaned = _clean_turn('[Replying to: "blah blah"] Actually do X instead')
        assert cleaned == "Actually do X instead"


class TestConsolidateParsing:
    """Stage 2 — JSON parsing, validation, and guard rails."""

    def test_parses_fenced_json(self):
        from zellandine.consolidate import _parse_json_array

        raw = '```json\n[{"target":"memory","action":"add","content":"x"}]\n```'
        assert len(_parse_json_array(raw)) == 1

    def test_parses_wrapped_object(self):
        from zellandine.consolidate import _parse_json_array

        raw = '{"proposals": [{"target":"memory","action":"add","content":"x"}]}'
        assert len(_parse_json_array(raw)) == 1

    def test_invalid_target_rejected(self):
        from zellandine.consolidate import _to_proposal

        assert _to_proposal({"target": "bogus", "action": "add", "content": "x"},
                            fallback_id="d-1") is None

    def test_confidence_clamped(self):
        from zellandine.consolidate import _to_proposal

        p = _to_proposal({"target": "memory", "action": "add", "content": "x",
                          "confidence": 5}, fallback_id="d-1")
        assert p is not None and p.confidence == 1.0

    def test_low_confidence_filtered(self):
        from zellandine.collect import CollectionResult, Episode
        from zellandine.consolidate import consolidate

        class FakeProvider:
            name = "fake"
            def consolidate(self, episodes_text, context=""):
                return '[{"target":"memory","action":"add","content":"x","confidence":0.5}]'
            def synthesize(self, *a, **k):
                return "[]"

        collected = CollectionResult(episodes=[Episode("s", "t", "info", "hello there")])
        res = consolidate(collected, provider=FakeProvider(), min_confidence=0.7)
        assert len(res.proposals) == 0

    def test_skill_remove_blocked(self):
        from zellandine.consolidate import Proposal, _passes_guards

        p = Proposal(id="d", target="skill", action="remove", content="x",
                     reason="", confidence=0.99)
        assert _passes_guards(p, 0.7, False) is False

    def test_max_proposals_clamped(self):
        from zellandine.collect import CollectionResult, Episode
        from zellandine.consolidate import consolidate

        class FakeProvider:
            name = "fake"
            def consolidate(self, episodes_text, context=""):
                import json as _j
                return _j.dumps([
                    {"target": "memory", "action": "add", "content": f"e{i}",
                     "confidence": 0.9} for i in range(10)
                ])
            def synthesize(self, *a, **k):
                return "[]"

        collected = CollectionResult(episodes=[Episode("s", "t", "info", "hello there")])
        res = consolidate(collected, provider=FakeProvider(), max_proposals=5)
        assert len(res.proposals) == 5


class TestProposalValidation:
    """Stage 2 — reject malformed proposals that would fail at apply time."""

    def test_replace_without_target_entry_rejected(self):
        from zellandine.consolidate import _to_proposal

        p = _to_proposal(
            {"target": "memory", "action": "replace", "content": "new text"},
            fallback_id="d-1",
        )
        assert p is None

    def test_replace_with_target_entry_accepted(self):
        from zellandine.consolidate import _to_proposal

        p = _to_proposal(
            {"target": "memory", "action": "replace", "content": "new text",
             "target_entry": "old text"},
            fallback_id="d-1",
        )
        assert p is not None and p.action == "replace"

    def test_remove_without_target_entry_rejected(self):
        from zellandine.consolidate import _to_proposal

        p = _to_proposal(
            {"target": "memory", "action": "remove", "confidence": 0.9},
            fallback_id="d-1",
        )
        assert p is None

    def test_skill_patch_without_old_string_rejected(self):
        from zellandine.consolidate import _to_proposal

        p = _to_proposal(
            {"target": "skill", "action": "patch", "content": "x",
             "skill_name": "foo", "new_string": "y"},
            fallback_id="d-1",
        )
        assert p is None

    def test_skill_patch_without_skill_name_rejected(self):
        from zellandine.consolidate import _to_proposal

        p = _to_proposal(
            {"target": "skill", "action": "patch", "content": "x",
             "old_string": "a", "new_string": "b"},
            fallback_id="d-1",
        )
        assert p is None

    def test_complete_skill_patch_accepted(self):
        from zellandine.consolidate import _to_proposal

        p = _to_proposal(
            {"target": "skill", "action": "patch", "content": "x",
             "skill_name": "foo", "old_string": "a", "new_string": "b"},
            fallback_id="d-1",
        )
        assert p is not None and p.skill_name == "foo"


class TestDedup:
    """Stage 2 — add-proposals that duplicate existing memory are dropped."""

    class _FakeProvider:
        name = "fake"

        def __init__(self, payload):
            self._payload = payload

        def consolidate(self, episodes_text, context=""):
            return self._payload

        def synthesize(self, *a, **k):
            return "[]"

    def _collected(self):
        from zellandine.collect import CollectionResult, Episode

        return CollectionResult(episodes=[Episode("s", "t", "info", "hello there friend")])

    def test_duplicate_add_dropped(self):
        from zellandine.consolidate import consolidate

        payload = (
            '[{"target":"memory","action":"add",'
            '"content":"Based in Hanoi, Vietnam. Timezone GMT+7. Never greet with assumed time of day.",'
            '"confidence":0.95}]'
        )
        existing = [
            "Based in Hanoi, Vietnam. Timezone GMT+7. NEVER greet with assumed time-of-day — always check the real Hanoi clock first."
        ]
        res = consolidate(
            self._collected(),
            provider=self._FakeProvider(payload),
            existing_entries=existing,
            min_confidence=0.7,
        )
        assert len(res.proposals) == 0

    def test_novel_add_kept(self):
        from zellandine.consolidate import consolidate

        payload = (
            '[{"target":"memory","action":"add",'
            '"content":"User keeps a Readwise account auto-forwarded via an n8n Telegram bot.",'
            '"confidence":0.9}]'
        )
        existing = ["Based in Hanoi, Vietnam. Timezone GMT+7."]
        res = consolidate(
            self._collected(),
            provider=self._FakeProvider(payload),
            existing_entries=existing,
            min_confidence=0.7,
        )
        assert len(res.proposals) == 1

    def test_replace_not_subject_to_dedup(self):
        # A replace explicitly updates an existing entry — must NOT be dropped
        # for overlapping with it.
        from zellandine.consolidate import consolidate

        payload = (
            '[{"target":"memory","action":"replace",'
            '"content":"Based in Hanoi, Vietnam. Timezone GMT+7. Prefers metric units.",'
            '"target_entry":"Based in Hanoi, Vietnam. Timezone GMT+7.",'
            '"confidence":0.9}]'
        )
        existing = ["Based in Hanoi, Vietnam. Timezone GMT+7."]
        res = consolidate(
            self._collected(),
            provider=self._FakeProvider(payload),
            existing_entries=existing,
            min_confidence=0.7,
        )
        assert len(res.proposals) == 1


class TestRunCyclePrune:
    """Orchestrator wires prune (Stage 3) into the cycle."""

    def _patch_hermes(self, monkeypatch, memory):
        from zellandine import hermes_api

        monkeypatch.setattr(hermes_api, "read_memory",
                            lambda: {"memory": memory, "user": []})
        monkeypatch.setattr(hermes_api, "memory_context_block",
                            lambda: {"memory": "\n".join(memory), "user": "(empty)"})
        monkeypatch.setattr(hermes_api, "skill_context_block", lambda: "(none)")
        monkeypatch.setattr(hermes_api, "read_session_digests", lambda limit=14: [
            {"session_id": "s1", "title": "t", "started_at": None,
             "message_count": 3, "source": "cli",
             "user_turns": ["please do something useful here for me"]}])
        monkeypatch.setattr(hermes_api, "read_cron_outputs", lambda *a, **k: [])

    def test_cycle_surfaces_duplicate_memory(self, tmp_path, monkeypatch):
        from zellandine import run
        from zellandine.config import Config

        self._patch_hermes(monkeypatch, [
            "User prefers concise British English replies.",
            "User likes concise replies in British English.",
        ])
        cfg = Config()
        cfg.llm = {"provider": "offline"}  # offline consolidation yields nothing
        summary = run.run_cycle(config=cfg, depth="full", dry_run=True,
                               artifact_root=tmp_path)
        assert summary["proposal_count"] >= 1

    def test_light_depth_skips_prune(self, tmp_path, monkeypatch):
        from zellandine import run
        from zellandine.config import Config

        self._patch_hermes(monkeypatch, [
            "User prefers concise British English replies.",
            "User likes concise replies in British English.",
        ])
        cfg = Config()
        cfg.llm = {"provider": "offline"}
        summary = run.run_cycle(config=cfg, depth="light", dry_run=True,
                               artifact_root=tmp_path)
        # light = collect + consolidate only; no prune, no synthesis
        assert summary["proposal_count"] == 0
        assert summary["insight_count"] == 0


class TestProviderResilience:
    """An unattended cycle must survive transient LLM/provider failures."""

    class _Boom:
        name = "boom"

        def consolidate(self, *a, **k):
            raise RuntimeError("api down")

        def synthesize(self, *a, **k):
            raise RuntimeError("api down")

    def _collected(self):
        from zellandine.collect import CollectionResult, Episode

        return CollectionResult(episodes=[Episode("s", "t", "info", "hello there friend")])

    def test_consolidate_survives_provider_error(self):
        from zellandine.consolidate import consolidate

        res = consolidate(self._collected(), provider=self._Boom())
        assert res.proposals == []
        assert "error" in (res.model_used or "").lower()

    def test_synthesize_survives_provider_error(self):
        from zellandine.synthesize import synthesize

        res = synthesize(self._collected(), [], provider=self._Boom())
        assert res.insights == []


class TestTimeoutBudget:
    """Cron must finish under Hermes' 120s script limit."""

    def test_provider_timeout_configurable(self):
        from zellandine.providers import OpenAICompatibleProvider

        p = OpenAICompatibleProvider(base_url="x", api_key="y", model="m", timeout=33)
        assert p.timeout == 33

    def test_provider_default_timeout(self):
        from zellandine.providers import OpenAICompatibleProvider

        p = OpenAICompatibleProvider(base_url="x", api_key="y", model="m")
        assert p.timeout <= 60

    def test_build_provider_threads_timeout(self, monkeypatch):
        from zellandine.config import Config, build_provider

        monkeypatch.setenv("OPENROUTER_API_KEY", "k")
        cfg = Config()
        cfg.llm = {"provider": "openrouter", "timeout": 33}
        prov = build_provider(cfg)
        assert getattr(prov, "timeout", None) == 33

    def _patch_hermes(self, monkeypatch):
        from zellandine import hermes_api

        monkeypatch.setattr(hermes_api, "read_memory",
                            lambda: {"memory": ["a fact"], "user": []})
        monkeypatch.setattr(hermes_api, "memory_context_block",
                            lambda: {"memory": "a fact", "user": "(empty)"})
        monkeypatch.setattr(hermes_api, "skill_context_block", lambda: "(none)")
        monkeypatch.setattr(hermes_api, "read_session_digests", lambda limit=14: [
            {"session_id": "s", "title": "t", "started_at": None,
             "message_count": 3, "source": "cli",
             "user_turns": ["please do a thing here for me"]}])
        monkeypatch.setattr(hermes_api, "read_cron_outputs", lambda *a, **k: [])

    def test_skips_synthesis_when_over_budget(self, tmp_path, monkeypatch):
        from zellandine import run
        from zellandine.config import Config

        self._patch_hermes(monkeypatch)
        cfg = Config()
        cfg.llm = {"provider": "offline"}
        clock = iter([0.0, 100.0])  # start, then pre-synthesis check (over 60s budget)
        summary = run.run_cycle(config=cfg, depth="full", dry_run=True,
                               artifact_root=tmp_path, time_budget_s=60.0,
                               clock=lambda: next(clock))
        assert summary["synthesis_skipped"] is True
        assert summary["insight_count"] == 0

    def test_runs_synthesis_within_budget(self, tmp_path, monkeypatch):
        from zellandine import run
        from zellandine.config import Config

        self._patch_hermes(monkeypatch)
        cfg = Config()
        cfg.llm = {"provider": "offline"}
        clock = iter([0.0, 1.0])  # well within budget
        summary = run.run_cycle(config=cfg, depth="full", dry_run=True,
                               artifact_root=tmp_path, time_budget_s=60.0,
                               clock=lambda: next(clock))
        assert summary["synthesis_skipped"] is False

    def test_budget_falls_back_to_config_when_unset(self, tmp_path, monkeypatch):
        # When run_cycle isn't given an explicit budget (as the cron script does),
        # it must use the configured time_budget_s.
        from zellandine import run
        from zellandine.config import Config

        self._patch_hermes(monkeypatch)
        cfg = Config()
        cfg.llm = {"provider": "offline"}
        cfg.time_budget_s = 5.0
        clock = iter([0.0, 10.0])  # 10s elapsed > config budget 5s ⇒ skip
        summary = run.run_cycle(config=cfg, depth="full", dry_run=True,
                               artifact_root=tmp_path, clock=lambda: next(clock))
        assert summary["synthesis_skipped"] is True

    def test_config_default_budget_is_generous(self):
        from zellandine.config import Config

        assert Config().time_budget_s >= 120


class TestConfig:
    """Config loading + provider construction."""

    def test_defaults_when_missing(self, tmp_path):
        from zellandine.config import load_config

        cfg = load_config(tmp_path / "nope.yaml")
        assert cfg.apply_mode == "manual"
        assert cfg.max_proposals == 5

    def test_minimal_yaml_parsing(self, tmp_path):
        from zellandine.config import load_config

        p = tmp_path / "config.yaml"
        p.write_text(
            "apply_mode: dry-run\nmax_proposals: 3\nllm:\n  provider: offline\n",
            encoding="utf-8",
        )
        cfg = load_config(p)
        assert cfg.apply_mode == "dry-run"
        assert cfg.max_proposals == 3
        assert cfg.llm["provider"] == "offline"

    def test_hash_inside_quoted_value_preserved(self, tmp_path):
        from zellandine.config import _minimal_yaml

        parsed = _minimal_yaml('model: "glm#4"\nschedule: "0 2 * * *"  # nightly\n')
        assert parsed["model"] == "glm#4"
        assert parsed["schedule"] == "0 2 * * *"

    def test_offline_provider_when_no_creds(self):
        from zellandine.config import Config, build_provider

        cfg = Config()
        prov = build_provider(cfg)
        assert prov.name == "offline-marker"

    def test_zai_coding_preset_uses_coding_endpoint(self, monkeypatch):
        from zellandine.config import Config, build_provider, PROVIDER_PRESETS

        assert "zai-coding" in PROVIDER_PRESETS
        monkeypatch.setenv("GLM_API_KEY", "k")
        cfg = Config()
        cfg.llm = {"provider": "zai-coding"}
        prov = build_provider(cfg)
        assert prov.base_url == "https://api.z.ai/api/coding/paas/v4"
        assert "glm" in prov.model

    def test_openai_provider_falls_back_without_key(self, monkeypatch):
        from zellandine.config import Config, build_provider

        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        cfg = Config()
        cfg.llm = {"provider": "openrouter"}
        prov = build_provider(cfg)
        # No key in env → graceful fallback to offline.
        assert prov.name == "offline-marker"


class TestApplySelection:
    """Apply — selection logic guard rails."""

    def test_manual_requires_approved(self):
        from zellandine.apply import _should_apply

        p = {"approved": False, "confidence": 0.99, "risk": "low"}
        assert _should_apply(p, auto=False, auto_threshold=0.9,
                             priority=None, target_kind=None) is False

    def test_auto_requires_high_conf_low_risk(self):
        from zellandine.apply import _should_apply

        hi = {"confidence": 0.95, "risk": "low"}
        med = {"confidence": 0.95, "risk": "medium"}
        assert _should_apply(hi, auto=True, auto_threshold=0.9,
                            priority=None, target_kind=None) is True
        assert _should_apply(med, auto=True, auto_threshold=0.9,
                            priority=None, target_kind=None) is False

    def test_apply_artifact_backs_up_and_applies_only_approved(self, tmp_path, monkeypatch):
        from zellandine import apply as zapply, hermes_api
        from zellandine.artifact import Manifest, write_artifact, read_manifest
        from zellandine.consolidate import Proposal

        calls = []
        monkeypatch.setattr(hermes_api, "snapshot_memory",
                            lambda d: calls.append("snapshot") or ["MEMORY.md"])
        monkeypatch.setattr(hermes_api, "apply_memory",
                            lambda **kw: calls.append(("apply", kw["action"])) or {"ok": True})

        props = [
            Proposal(id="a1", target="memory", action="add", content="x",
                     reason="r", confidence=0.95, approved=True),
            Proposal(id="a2", target="memory", action="add", content="y",
                     reason="r", confidence=0.95, approved=False),
        ]
        art = tmp_path / "d"
        write_artifact(art, Manifest(artifact_id="d"), props, "rep")

        res = zapply.apply_artifact(art, auto=False)
        assert res["applied"] == 1                  # only the approved one
        assert "snapshot" in calls                   # backup taken before mutation
        assert read_manifest(art).status == "applied"
        assert (art / "audit.jsonl").exists()

    def test_failed_mutation_not_counted_as_applied(self, tmp_path, monkeypatch):
        from zellandine import apply as zapply, hermes_api
        from zellandine.artifact import Manifest, write_artifact, read_manifest
        from zellandine.consolidate import Proposal

        monkeypatch.setattr(hermes_api, "snapshot_memory", lambda d: ["MEMORY.md"])
        # MemoryStore returns success:False (no exception) when nothing matched.
        monkeypatch.setattr(hermes_api, "apply_memory",
                            lambda **kw: {"success": False, "error": "no match"})
        props = [Proposal(id="a1", target="memory", action="replace", content="x",
                          reason="r", confidence=0.95, approved=True, target_entry="old")]
        art = tmp_path / "d"
        write_artifact(art, Manifest(artifact_id="d"), props, "rep")

        res = zapply.apply_artifact(art, auto=False)
        assert res["applied"] == 0
        assert res["results"][0]["ok"] is False
        assert read_manifest(art).status != "applied"
