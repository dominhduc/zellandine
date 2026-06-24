# Hermes Dream — Architecture Document

> **A native dreaming system for Hermes Agent.** Sleep-inspired memory consolidation, skill evolution, and self-reflection — built on Hermes' own APIs, safe by design, contributing back to the community.

---

## 1. The Problem

Every Hermes session starts with the same ~3,700 chars of injected memory. The agent forgets corrections from three sessions ago. Skills don't evolve unless manually patched. No system connects dots across sessions, surfaces patterns, or prunes stale knowledge.

Hermes has all the **primitives** — `memory()`, `skill_manage()`, `session_search()`, `cron` — but no **orchestration loop** that uses them during idle time to consolidate, prune, and improve.

## 2. Design Principles

| Principle | What it means |
|-----------|--------------|
| **Hermes-native** | Uses `memory()`, `skill_manage()`, `session_search()`, `cron` APIs directly. No parallel memory store. No flat-file duplication. |
| **Safe by default** | Every proposed change is staged in an artifact. Nothing mutates live state without review + explicit apply. Full revert via backups. |
| **Cheap to run** | Nightly cycle costs < $0.03 in API tokens. Uses the agent's existing model. No vector DB required. |
| **Observable** | Dream journal delivered to Telegram. Artifacts inspectable on disk. Run ledger for auditability. |
| **Configurable** | Fully dormant by default. Operator opts in per feature. Schedule, depth, and delivery are all configurable. |
| **Community-ready** | Ships as a proper Hermes plugin with skill, cron integration, and documentation. MIT licensed. |

## 3. Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    HERMES DREAM CYCLE                            │
│                   (cron: nightly, configurable)                  │
│                                                                 │
│  ┌──────────┐    ┌──────────────┐    ┌──────────┐    ┌───────┐ │
│  │ COLLECT  │───▶│ CONSOLIDATE  │───▶│  PRUNE   │───▶│SYNTH  │ │
│  │ (NREM-1) │    │  (NREM-2)    │    │(downscal)│    │ (REM) │ │
│  └──────────┘    └──────────────┘    └──────────┘    └───────┘ │
│       │                 │                 │              │      │
│       ▼                 ▼                 ▼              ▼      │
│  session_search    memory()          memory()       skill_     │
│  cron outputs      skill_manage()    remove()       manage()   │
│  error logs        (patch)                          (patch)    │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                    STAGE → REVIEW → APPLY                 │   │
│  │                                                          │   │
│  │  artifacts/dream-YYYY-MM-DD/                             │   │
│  │    manifest.json    — run metadata, timestamps           │   │
│  │    report.md        — human-readable dream report        │   │
│  │    proposals.jsonl  — staged changes with provenance     │   │
│  │    audit.jsonl      — every action, timestamped          │   │
│  │    backup/          — pre-apply snapshots                │   │
│  └──────────────────────────────────────────────────────────┘   │
│                          │                                      │
│                          ▼                                      │
│  ┌──────────┐    ┌──────────────┐    ┌───────────────────────┐  │
│  │ DELIVER  │    │  JOURNAL     │    │  MORNING BRIEF HOOK   │  │
│  │ Telegram │    │  Obsidian    │    │  (inject into existing│  │
│  │ summary  │    │  vault       │    │   morning brief cron) │  │
│  └──────────┘    └──────────────┘    └───────────────────────┘  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## 4. The Five Stages

### Stage 1 — COLLECT (Sleep Onset / Hippocampal Replay)

**Goal:** Gather the raw material from the day.

**Inputs:**
- `session_search(limit=N, sort="newest")` — recent session digests
- Cron job output logs (`~/.hermes/cron/output/`) — what ran, what failed
- Previous dream artifact (if any) — continuity marker
- System prompt snapshot — current memory + skill state

**Process:**
- Extract compact session digests (title, first/last messages, key turns)
- Read cron run statuses and errors from the last 24h
- Identify "episodes": decisions, corrections, new tasks, errors, preferences

**Output:** `episodes.jsonl` — one JSON object per salient episode

```json
{
  "source": "session:abc123",
  "timestamp": "2026-06-24T15:30:00+07:00",
  "type": "correction",
  "content": "User corrected greeting time: said 'Good morning' at 20:00",
  "existing_memory_match": "Based in Hanoi... NEVER greet with assumed time-of-day",
  "severity": "high"
}
```

### Stage 2 — CONSOLIDATE (NREM-2 / Declarative Memory)

**Goal:** Convert episodes into structured proposals for memory, skills, and user profile.

**Process (single LLM pass with structured output):**

The model receives:
1. Collected episodes (from Stage 1)
2. Current memory state (both stores, via `memory(action=read)`)
3. Current user profile
4. Skill list with descriptions

The model outputs proposals in structured JSON:

```json
[
  {
    "id": "dream-001",
    "target": "memory",
    "action": "add",
    "content": "Cron job greeting fix: Inbox Digest now checks `date '+%H'` before greeting",
    "target_entry": null,
    "reason": "Recurring correction — user raised greeting-time errors 3+ times",
    "confidence": 0.95,
    "risk": "low",
    "provenance": "session:abc123, session:def456, session:ghi789"
  },
  {
    "id": "dream-002",
    "target": "skill",
    "action": "patch",
    "skill_name": "alfred-email-deletion",
    "old_string": "Dán nhãn: /usr/local/bin/alfred-email apply label:X \"subject:...\" is:unread",
    "new_string": "Dán nhãn: /usr/local/bin/alfred-email apply label:X \"subject:...\" (NEVER use is:unread)",
    "reason": "is:unread race condition caused silent labelling failures",
    "confidence": 0.90,
    "risk": "medium",
    "provenance": "session:abc123"
  }
]
```

**Proposal types:**

| Target | Actions | Hermes API |
|--------|---------|------------|
| `memory` | add, replace, remove | `memory(action=...)` |
| `user` | add, replace, remove | `memory(target="user", action=...)` |
| `skill` | patch, edit, create | `skill_manage(action=...)` |

### Stage 3 — PRUNE (Synaptic Downscaling)

**Goal:** Reduce noise. Forget what's stale. Merge what's duplicated.

**Process:**
- Scan all memory entries for:
  - **Duplicates** — same fact in different wording → merge
  - **Stale** — references to abandoned projects, dead tools, expired configs → flag for removal
  - **Contradictions** — new fact supersedes old → propose replacement
- Score each entry using:

```python
importance = (base_weight × recency_factor × reference_boost) / 8.0

# base_weight: 1.0 default, 2.0 if marked critical (⚠️), 0.5 if soft preference
# recency_factor: max(0.1, 1.0 - days_since_last_referenced / 180)
# reference_boost: log2(correction_count + 1)
```

- Entries scoring below 0.1 after 90 days → proposal to archive (not delete)

**Output:** Added to `proposals.jsonl` as removal/replace proposals.

### Stage 4 — SYNTHESIZE (REM / Associative Memory)

**Goal:** Connect dots. Surface patterns. Propose novel insights.

**Process (second LLM pass, higher temperature):**
- Cross-reference episodes across sessions
- Identify recurring themes: "User corrects greeting time every week" → systemic issue
- Surface non-obvious connections: "Three separate email failures all trace to is:unread queries" → pattern
- Generate 1-3 "dream insights" — suggestions, not facts

**Output:** Added to `report.md` under "Patterns & Insights" section. Not committed to memory — surfaced for human review.

### Stage 5 — REPORT (Wake / Dream Journal)

**Goal:** Deliver findings and update state.

**Outputs:**
1. **Dream report** — written to artifact `report.md`
2. **Telegram summary** — concise digest of proposals + insights (delivered if configured)
3. **Obsidian journal** — appended to `~/Documents/ObsidianVault/Dream/DREAMS.md`
4. **Morning brief hook** — proposals flagged as "high confidence + low risk" are injected into the existing morning brief for next-day review
5. **State update** — `last_dream_at` timestamp, `episode_count`, `proposal_count`

## 5. Safety Model

### The Artifact Gate

No proposal touches live state during the dream cycle. The flow is:

```
Dream cycle → STAGE proposals (artifact) → REPORT → [manual or auto review] → APPLY → live state
```

### Apply Modes

| Mode | Behaviour | Use case |
|------|-----------|----------|
| **Manual** (default) | Proposals staged. User reviews via `dream review`, approves/rejects, then `dream apply`. | Production, trust-building |
| **Auto (high-confidence only)** | Proposals with confidence ≥ 0.9 AND risk = "low" auto-apply. Everything else staged. | After trust is established |
| **Dry-run** | No writes at all. Report only. | Testing, first runs |

### Backups

Before any apply:
- `memory()` and `skill_manage()` are native APIs — they don't support pre-write snapshots
- Dream maintains its own backup: before apply, it snapshots the **current memory and skill state** to `artifact/backup/`
- Revert restores from backup snapshot

### Guard Rails

- Never propose changes to `SOUL.md` (persona) without explicit `--allow-soul` flag
- Never propose skill deletions — only patches and creates
- Memory removals require confidence ≥ 0.8
- Maximum 5 proposals per cycle (prevents runaway mutations)
- Proposals that reference sessions older than 7 days are downgraded to "suggestion" (no apply)

## 6. Plugin Structure

```
dreaming/
├── plugin.yaml              # Hermes plugin manifest
├── SKILL.md                 # Human-readable skill (loaded by agent on demand)
├── README.md                # Community docs
├── architecture.md          # This document
├── pyproject.toml           # Python package config
├── src/
│   └── dreaming/
│       ├── __init__.py
│       ├── cli.py           # `dreaming review|apply|revert|status|install-cron`
│       ├── collect.py       # Stage 1: session + cron data gathering
│       ├── consolidate.py   # Stage 2: episode → proposal extraction
│       ├── prune.py         # Stage 3: scoring + decay + dedup
│       ├── synthesize.py    # Stage 4: REM pattern detection
│       ├── report.py        # Stage 5: report + delivery
│       ├── artifact.py      # Artifact read/write/validate
│       ├── scoring.py       # Importance scoring + forgetting curves
│       ├── hermes_api.py    # Thin wrapper: calls memory(), skill_manage(), session_search()
│       ├── providers.py     # LLM provider abstraction (offline, openai-compatible)
│       └── state.py         # Dream state persistence (timestamps, counters)
├── scripts/
│   └── dream_cycle.sh       # Cron entry point (script-only, no agent tokens)
├── templates/
│   ├── consolidation_prompt.txt   # Stage 2 LLM prompt
│   ├── synthesis_prompt.txt       # Stage 4 LLM prompt
│   └── telegram_digest.txt        # Stage 5 delivery template
├── examples/
│   └── quickstart/          # Offline fixture for demo/testing
└── tests/
    ├── test_artifact.py
    ├── test_scoring.py
    ├── test_collect.py
    └── test_safety.py
```

## 7. Configuration

```yaml
# ~/.hermes/dreaming/config.yaml
schedule: "0 2 * * *"          # Nightly at 02:00 local
depth: "full"                   # "light" (collect+consolidate only) | "full" (all 5 stages)
apply_mode: "manual"            # "manual" | "auto-high-confidence" | "dry-run"
max_proposals: 5
min_confidence: 0.8             # Minimum to stage a proposal
auto_apply_threshold: 0.9       # Minimum for auto-apply (if mode=auto)
session_lookback: 14            # Sessions to scan
deliver: "telegram"             # "telegram" | "local" | "none"
obsidian_vault: "~/Documents/ObsidianVault"
obsidian_enabled: true
allow_soul_changes: false
forgetting:
  enabled: true
  half_life_days: 180           # Recency decay
  archive_threshold: 0.1        # Score below this → archive proposal
  min_age_days: 90              # Don't prune entries younger than this
model: null                     # null = use current Hermes model
```

## 8. Unique Value Proposition (vs existing repos)

| Feature | Hermes Dream | Pluton | hermes-dreaming | Auto-Dream | ScallopBot | REM-Sleep |
|---------|:------------:|:------:|:---------------:|:----------:|:----------:|:---------:|
| Uses native `memory()` API | ✅ | ❌ (flat file) | ❌ (flat file) | ❌ | ❌ | ❌ |
| Uses native `skill_manage()` | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Uses `session_search()` | ✅ | ❌ | ✅ (SQLite) | ❌ | ❌ | ❌ |
| NREM + REM stages | ✅ | ❌ | ❌ | ✅ | ✅ | ✅ |
| Forgetting curve | ✅ | ❌ | ❌ | ✅ | ✅ | ✅ (manual) |
| Telegram delivery | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Obsidian journal | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Safety gates (review/apply) | ✅ | ❌ | ✅ | ❌ | ❌ | ✅ |
| Skill evolution | ✅ | ❌ | ✅ | ❌ | ❌ | ❌ |
| Cron-native | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| Zero-vector-DB | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ |

**The key differentiator:** Every other plugin creates a *parallel memory store*. Hermes Dream operates on Hermes' *actual* memory and skill APIs — no second source of truth, no sync issues, no format mismatch.

## 9. API Surface (for community contribution)

### CLI Commands

```bash
# Run a dream cycle (manual or triggered by cron)
dreaming run [--depth full|light] [--dry-run]

# Review staged proposals
dreaming review [--latest | <artifact-id>]

# Apply approved proposals
dreaming apply <artifact-id> [--auto] [--dry-run]

# Revert an applied artifact
dreaming revert <artifact-id>

# Show status
dreaming status

# Install/update nightly cron
dreaming install-cron [--schedule "0 2 * * *"]

# Render digests
dreaming digest <artifact-id> [--weekly]
```

### Hermes Skill (SKILL.md)

The bundled skill lets the user trigger a dream cycle conversationally:

```
User: "Dream on today's sessions"
Agent: loads `dreaming` skill → runs consolidation → presents proposals → asks to apply
```

### Cron Integration

```bash
# Script-only nightly cycle (no agent tokens spent on orchestration)
dreaming install-cron --schedule "0 2 * * *"
# Creates a Hermes cron job with no_agent=true, script=dream_cycle.sh
```

## 10. Implementation Phases

### Phase 1 — MVP (Week 1-2)
- [ ] Plugin scaffold (`plugin.yaml`, `__init__.py`)
- [ ] Stage 1: `collect.py` — session_search + cron output reader
- [ ] Stage 2: `consolidate.py` — single-pass LLM extraction → proposals
- [ ] Stage 5: `report.py` — artifact write + Telegram digest
- [ ] `hermes_api.py` — wrapper around memory() + skill_manage()
- [ ] `cli.py` — run, review, apply, status
- [ ] Offline test fixture
- [ ] Safety: dry-run mode, backup snapshots, revert

### Phase 2 — Intelligence (Week 3-4)
- [ ] Stage 3: `prune.py` — importance scoring + forgetting curves
- [ ] Stage 4: `synthesize.py` — REM pattern detection
- [ ] `scoring.py` — full scoring engine
- [ ] Auto-apply mode (high-confidence threshold gating)
- [ ] Obsidian journal integration

### Phase 3 — Polish & Community (Week 5-6)
- [ ] Config system (`config.yaml`)
- [ ] `install-cron` command
- [ ] Quickstart demo + video
- [ ] README with comparison table
- [ ] Submit to Hermes plugin registry
- [ ] Blog post / community announcement

## 11. Cost Estimate

| Operation | Calls/cycle | Tokens | Est. Cost |
|-----------|:-----------:|:------:|:---------:|
| Session collection | 1-3 (session_search) | ~2K | $0.001 |
| Consolidation (Stage 2) | 1 LLM call | ~8K | $0.01 |
| Pruning (Stage 3) | 0 (deterministic) | 0 | $0 |
| Synthesis (Stage 4) | 1 LLM call | ~6K | $0.008 |
| Report + delivery | 1 LLM call | ~2K | $0.003 |
| **Total per nightly cycle** | ~4-5 | ~18K | **~$0.02** |

Annual cost: ~$7.30. Cheaper than a cup of coffee per month.

## 12. License

MIT — same as Hermes Agent. Community-owned, community-improved.
