"""Prompt template loader.

The templates in templates/*.txt are valid Python modules exposing
SYSTEM_PROMPT and USER_PROMPT_TEMPLATE string constants. We load them
by compiling in an isolated namespace (trusted, package-local files).
Falls back to built-in defaults if the files are missing.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "templates"

_FALLBACK_CONSOLIDATE_SYSTEM = (
    "You are a memory consolidation engine. Analyze session episodes and the "
    "agent's current memory, then output a JSON array of at most 5 proposals "
    "(fields: id, target[memory|user|skill], action[add|replace|remove|patch], "
    "content, target_entry, skill_name, old_string, new_string, reason, "
    "confidence[0-1], risk[low|medium|high], priority[low|normal|high], "
    "provenance). Be conservative. Return ONLY the JSON array."
)
_FALLBACK_CONSOLIDATE_USER = (
    "## Current Memory State\n{current_memory}\n\n## Current User Profile\n"
    "{current_user}\n\n## Installed Skills\n{skill_list}\n\n## Today's Episodes\n"
    "{episodes}\n\n## Proposals (JSON array, max 5):\n"
)
_FALLBACK_SYNTH_SYSTEM = (
    "You are a REM-sleep synthesis engine. Look across all episodes for "
    "patterns, connections, drift, and suggestions. Output a JSON array of at "
    "most 3 insights (fields: type[pattern|connection|suggestion|drift_alert], "
    "content, evidence, confidence). Return ONLY the JSON array."
)
_FALLBACK_SYNTH_USER = (
    "## Today's Episodes\n{episodes}\n\n## NREM Proposals\n{proposals}\n\n"
    "## Insights (JSON array, max 3):\n"
)


@lru_cache(maxsize=None)
def _load(name: str) -> tuple[str, str]:
    path = _TEMPLATES_DIR / name
    try:
        ns: dict[str, object] = {}
        exec(compile(path.read_text(encoding="utf-8"), str(path), "exec"), ns)
        system = str(ns.get("SYSTEM_PROMPT", "")).strip()
        user = str(ns.get("USER_PROMPT_TEMPLATE", "")).strip()
        if system and user:
            return system, user
    except Exception:
        pass
    return "", ""


def consolidation_prompts() -> tuple[str, str]:
    system, user = _load("consolidation_prompt.txt")
    return (
        system or _FALLBACK_CONSOLIDATE_SYSTEM,
        user or _FALLBACK_CONSOLIDATE_USER,
    )


def synthesis_prompts() -> tuple[str, str]:
    system, user = _load("synthesis_prompt.txt")
    return (
        system or _FALLBACK_SYNTH_SYSTEM,
        user or _FALLBACK_SYNTH_USER,
    )
