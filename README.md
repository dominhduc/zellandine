# Zellandine 🌙

> *Named after La Belle au Bois Dormant — the one who wakes wiser than she slept.*

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Hermes Plugin](https://img.shields.io/badge/Hermes-Plugin-FFD700.svg)](https://github.com/NousResearch/hermes-agent)

**A native dreaming system for [Hermes Agent](https://github.com/NousResearch/hermes-agent).**

Zellandine runs a nightly consolidation cycle — scanning recent sessions, extracting patterns, proposing memory and skill updates, and delivering a dream report. All through Hermes' own APIs. No parallel memory store. No flat-file drift. No vector database.

## TL;DR for agents

- **What it is:** a CLI (`zellandine`) + a `no_agent` nightly cron job that reads Hermes' real memory/sessions/skills, *stages* proposed changes into a reviewable artifact, and delivers a digest. It never mutates live state on its own.
- **Safe by default:** `apply_mode: manual`. The cycle only writes to `~/.hermes/zellandine/artifacts/<id>/`. Changing live memory requires an explicit `zellandine apply <id>`, which snapshots to `backup/` first and is fully revertable.
- **Cheap by default:** the LLM provider defaults to `offline` (a zero-cost marker scan, **$0**). Plugging in an OpenAI-compatible provider unlocks the smarter consolidate/synthesize stages.
- **Run it now:** `zellandine run --dry-run` (reports, writes nothing). Drop `--dry-run` to stage an artifact.
- **Inspect state:** `zellandine status`. **Review latest:** `zellandine review --latest`.

## Why

Every Hermes session starts with the same injected memory. The agent forgets corrections from three sessions ago. Skills don't evolve unless manually patched. No system connects dots across sessions, surfaces patterns, or prunes stale knowledge.

Zellandine gives Hermes what sleep gives a brain: **consolidation, pruning, and synthesis** — during idle time, safely, cheaply.

## The Dream Cycle

Five stages, inspired by the neuroscience of sleep:

| Stage | Name | What It Does | Provider |
|-------|------|-------------|----------|
| 1 | **Collect** (Sleep Onset) | Scan recent sessions + cron outputs → classified `Episode`s | none |
| 2 | **Consolidate** (NREM) | Extract structured `Proposal`s for memory/user/skill changes | LLM |
| 3 | **Prune** (Synaptic Downscaling) | Score entries, flag near-duplicates (Jaccard), suggest merges | none |
| 4 | **Synthesize** (REM) | Cross-session pattern detection → novel `Insight`s | LLM |
| 5 | **Report** (Wake) | Dream journal artifact + Telegram/local digest | none |

`--depth light` runs collect + consolidate only. With the default **offline** provider, the LLM stages run a zero-cost heuristic marker scan, so the whole cycle costs **$0**. With a real provider, a full nightly cycle is roughly **~$0.02/night (~$7/year)** — and is free entirely on a flat-rate plan (e.g. Z.ai GLM Coding Plan).

## Install

Requires Python 3.11+ and a working [Hermes Agent](https://github.com/NousResearch/hermes-agent) install at `~/.hermes`.

```bash
git clone https://github.com/dominhduc/zellandine.git
cd zellandine
python -m pip install -e .
```

> **PEP 668 note:** if your Hermes Python is an externally-managed system interpreter, `pip install -e` may be blocked. In that case run the cycle module directly (`python -m zellandine.cli ...`) or expose a small PATH wrapper at `~/.local/bin/zellandine` that calls it. The cron entrypoint installed below self-bootstraps `sys.path` and does **not** require the package to be pip-installed.

Then copy the example config and point the LLM at a provider (optional — omit to stay offline/$0):

```bash
mkdir -p ~/.hermes/zellandine
cp config.example.yaml ~/.hermes/zellandine/config.yaml
```

## Command reference

```
zellandine <command> [flags]
```

| Command | Purpose | Key flags |
|---------|---------|-----------|
| `run` | Run a dream cycle, stage an artifact, print the digest | `--dry-run`, `--depth full\|light`, `--sessions N`, `--live-root`, `--artifact-root` |
| `review [id]` | Print an artifact's `report.md` + proposal path | `--latest` (or omit `id`) |
| `apply <id>` | Apply approved proposals via Hermes' native APIs (backs up first) | `--auto`, `--dry-run`, `--priority low\|normal\|high`, `--target-kind memory\|user\|skill` |
| `revert <id>` | Restore memory/skills from an applied artifact's `backup/` | `--yes` |
| `status` | Show last-dream time and lifetime cycle/proposal/apply counts | — |
| `install-cron` | Register the nightly `no_agent` dream cron job in Hermes | `--schedule "0 2 * * *"` |
| `digest <id>` | Re-render the Telegram-style digest for an artifact | `--weekly` |

### Typical flow

```bash
zellandine run --dry-run            # 1. see what it would do, write nothing
zellandine run                      # 2. stage a real artifact
zellandine review --latest          # 3. read the dream report + proposals
zellandine apply <artifact-id>      # 4. apply approved changes (revertable)
zellandine install-cron             # 5. schedule it nightly (02:00 local)
```

To approve specific proposals, edit `proposals.jsonl` in the artifact (mark entries `"approved"`), or use `apply --auto` to take only high-confidence ones (≥ `auto_apply_threshold`).

## Safety Model

Every proposed change is staged in a reviewable artifact directory:

```
~/.hermes/zellandine/artifacts/dream-2026-06-24/
  manifest.json     — run metadata, timestamps, counts
  report.md         — human-readable dream report
  proposals.jsonl   — staged changes with provenance + confidence
  audit.jsonl       — every action, timestamped
  backup/           — pre-apply snapshots of memory/skills
```

Guard rails: max 5 proposals per cycle, no `SOUL.md` changes (`allow_soul_changes: false`), no skill deletes, memory removals require high confidence. Nothing mutates live state without `apply`. Full revert from `backup/`.

## What Makes It Different

Other dream plugins create a **parallel memory store** — their own files that drift out of sync with Hermes' canonical memory.

Hermes' own memory is `§`-delimited markdown at `~/.hermes/memories/{MEMORY,USER}.md`, mutated through native modules (`MemoryStore`) that enforce locking and drift detection. Zellandine is the only plugin that reads and writes through that **real path** — staging proposals and applying them via Hermes' own tools — so there's no second source of truth:

| Concern | Hermes interface Zellandine uses |
|---------|----------------------------------|
| Memory | `tools.memory_tool.MemoryStore.add/replace/remove` |
| Skills | `tools.skill_manager_tool.skill_manage(action="patch", …)` |
| Sessions | `hermes_state.SessionDB` (`list_sessions_rich`, `search_messages`) |
| Cron | `cron.jobs.create_job(..., no_agent=True)` — stdout delivered verbatim |

## Configuration

`~/.hermes/zellandine/config.yaml` (see [`config.example.yaml`](config.example.yaml)). All keys have built-in defaults — the file is optional.

```yaml
schedule: "0 2 * * *"        # nightly at 02:00 local
depth: "full"                # full (all 5 stages) | light (collect + consolidate)
apply_mode: "manual"         # manual | auto-high-confidence | dry-run
max_proposals: 5
min_confidence: 0.7          # minimum confidence to stage a proposal
auto_apply_threshold: 0.9    # minimum for apply --auto
session_lookback: 14         # recent sessions to scan
deliver: "telegram"          # telegram | local | none
time_budget_s: 300           # skip REM synthesis if consolidation ran long
allow_soul_changes: false
model: null                  # null = use current Hermes model

# LLM provider for the consolidate/synthesize stages.
# provider: "offline"  → zero-cost marker scan (default).
# Use a preset name (openrouter | zai | zai-coding | glm | groq) OR set
# base_url/api_key_env/model explicitly. The API key is read from the env
# var named by api_key_env (typically loaded from ~/.hermes/.env).
llm:
  provider: "offline"        # offline | openrouter | zai | zai-coding | glm | groq | openai-compatible
  base_url: ""               # overrides the preset endpoint
  api_key_env: ""            # e.g. OPENROUTER_API_KEY / GLM_API_KEY / GROQ_API_KEY
  model: ""                  # e.g. z-ai/glm-4.6
  temperature: 0.3
  max_tokens: 4096
  timeout: 45                # per-call timeout (s); a hung endpoint degrades to offline

forgetting:
  enabled: true
  half_life_days: 180
  archive_threshold: 0.1
  min_age_days: 90
```

If credentials or endpoint are missing, the provider **degrades gracefully to offline** so the cycle always runs.

## Development

```bash
python -m pip install -e ".[dev]"
pytest -q
```

See [`docs/architecture.md`](docs/architecture.md) for the full design.

## License

MIT — same as Hermes Agent.

## Acknowledgements

Architecture informed by research on sleep-consolidated memory (SCM), bio-inspired cognitive architectures (ScallopBot), staged self-improvement (hermes-dreaming), and the neuroscience of NREM/REM cycles.
