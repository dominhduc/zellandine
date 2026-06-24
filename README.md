# Zellandine 🌙

> *Named after La Belle au Bois Dormant — the one who wakes wiser than she slept.*

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Hermes Plugin](https://img.shields.io/badge/Hermes-Plugin-FFD700.svg)](https://github.com/NousResearch/hermes-agent)

**A native dreaming system for [Hermes Agent](https://github.com/NousResearch/hermes-agent).**

Zellandine runs a nightly consolidation cycle — scanning recent sessions, extracting patterns, proposing memory and skill updates, and delivering a dream report. All through Hermes' own APIs. No parallel memory store. No flat-file drift. No vector database.

## Why

Every Hermes session starts with the same injected memory. The agent forgets corrections from three sessions ago. Skills don't evolve unless manually patched. No system connects dots across sessions, surfaces patterns, or prunes stale knowledge.

Zellandine gives Hermes what sleep gives a brain: **consolidation, pruning, and synthesis** — during idle time, safely, cheaply.

## The Dream Cycle

Five stages, inspired by the neuroscience of sleep:

| Stage | Name | What It Does | Cost |
|-------|------|-------------|------|
| 1 | **Collect** (Sleep Onset) | Scan recent sessions via `session_search()`, read cron outputs | ~$0.001 |
| 2 | **Consolidate** (NREM) | Extract structured proposals for memory/skill/user changes | ~$0.01 |
| 3 | **Prune** (Synaptic Downscaling) | Score entries, decay stale ones, flag duplicates | $0 |
| 4 | **Synthesize** (REM) | Cross-session pattern detection, novel insights | ~$0.008 |
| 5 | **Report** (Wake) | Dream journal to Obsidian + Telegram digest | ~$0.003 |

**Total: ~$0.02/night, ~$7/year.**

## Install

```bash
hermes plugins install YOUR_GITHUB/zellandine --enable
```

## Quick Start

```bash
# Run a dream cycle now (dry-run)
zellandine run --dry-run

# Review staged proposals
zellandine review --latest

# Apply approved proposals
zellandine apply <artifact-id>

# Install nightly cron (2 AM local)
zellandine install-cron --schedule "0 2 * * *"
```

## Safety Model

Every proposed change is staged in a reviewable artifact directory:

```
artifacts/dream-2026-06-24/
  manifest.json     — run metadata, timestamps
  report.md         — human-readable dream report
  proposals.jsonl   — staged changes with provenance
  audit.jsonl       — every action, timestamped
  backup/           — pre-apply snapshots
```

Nothing mutates live state without review + explicit apply. Full revert from backups.

## What Makes It Different

Every other dream plugin (Pluton, hermes-dreaming, Auto-Dream) creates a **parallel memory store** — flat markdown files that drift out of sync with Hermes' actual JSON memory.

Zellandine is the only one that calls Hermes' **real APIs**:

- `memory(action="add|replace|remove")` — direct mutation
- `skill_manage(action="patch|create|edit")` — skill evolution
- `session_search(query, limit)` — rich session recall

No second source of truth. No sync issues.

## Configuration

```yaml
# ~/.hermes/zellandine/config.yaml
schedule: "0 2 * * *"
depth: "full"               # full | light
apply_mode: "manual"        # manual | auto-high-confidence | dry-run
max_proposals: 5
session_lookback: 14
deliver: "telegram"          # telegram | local | none
```

## Development

```bash
python -m pip install -e ".[dev]"
pytest -q
```

## License

MIT — same as Hermes Agent.

## Acknowledgements

Architecture informed by research on sleep-consolidated memory (SCM), bio-inspired cognitive architectures (ScallopBot), staged self-improvement (hermes-dreaming), and the neuroscience of NREM/REM cycles.
