"""Configuration loading and provider construction.

Config resolution order:
1. Explicit path passed to load_config()
2. ~/.hermes/zellandine/config.yaml
3. Built-in defaults (mirrors config.example.yaml)

YAML is parsed with PyYAML if available, otherwise a tiny built-in
parser handles the flat key/value + one nested block this config uses.
No hard dependency on PyYAML.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .providers import (
    DreamProvider,
    OfflineMarkerProvider,
    OpenAICompatibleProvider,
)

try:
    from hermes_constants import get_hermes_home  # type: ignore
except Exception:

    def get_hermes_home() -> Path:
        return Path.home() / ".hermes"


DEFAULTS: dict[str, Any] = {
    "schedule": "0 2 * * *",
    "depth": "full",
    "apply_mode": "manual",
    "max_proposals": 5,
    "min_confidence": 0.7,
    "auto_apply_threshold": 0.9,
    "session_lookback": 14,
    "deliver": "telegram",
    # Skip the optional REM synthesis only if consolidation already ran past
    # this many seconds. Generous by default — the cron script timeout is the
    # real ceiling (raise it via cron.script_timeout_seconds for slow models).
    "time_budget_s": 300,
    "obsidian_enabled": False,
    "obsidian_vault": "~/Documents/ObsidianVault",
    "allow_soul_changes": False,
    "model": None,
    # LLM provider for consolidate/synthesize. "offline" = zero-cost marker scan.
    "llm": {
        "provider": "offline",  # offline | openai-compatible
        "base_url": "",
        "api_key_env": "",
        "model": "",
        "temperature": 0.3,
        "max_tokens": 4096,
        "timeout": 45,
    },
    "forgetting": {
        "enabled": True,
        "half_life_days": 180,
        "archive_threshold": 0.1,
        "min_age_days": 90,
    },
}

# Known OpenAI-compatible endpoints, keyed by short provider name.
PROVIDER_PRESETS: dict[str, dict[str, str]] = {
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY",
        "model": "z-ai/glm-4.6",
    },
    "zai": {
        "base_url": "https://api.z.ai/api/paas/v4",
        "api_key_env": "GLM_API_KEY",
        "model": "glm-4.6",
    },
    # Z.ai "GLM Coding Plan" — flat-rate/free for subscribers, different endpoint
    # from pay-as-you-go (which 429s once quota is spent).
    "zai-coding": {
        "base_url": "https://api.z.ai/api/coding/paas/v4",
        "api_key_env": "GLM_API_KEY",
        "model": "glm-4.5",
    },
    "glm": {
        "base_url": "https://api.z.ai/api/paas/v4",
        "api_key_env": "GLM_API_KEY",
        "model": "glm-4.6",
    },
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "api_key_env": "GROQ_API_KEY",
        "model": "llama-3.3-70b-versatile",
    },
}


@dataclass
class Config:
    schedule: str = DEFAULTS["schedule"]
    depth: str = DEFAULTS["depth"]
    apply_mode: str = DEFAULTS["apply_mode"]
    max_proposals: int = DEFAULTS["max_proposals"]
    min_confidence: float = DEFAULTS["min_confidence"]
    auto_apply_threshold: float = DEFAULTS["auto_apply_threshold"]
    session_lookback: int = DEFAULTS["session_lookback"]
    deliver: str = DEFAULTS["deliver"]
    time_budget_s: float = DEFAULTS["time_budget_s"]
    obsidian_enabled: bool = DEFAULTS["obsidian_enabled"]
    obsidian_vault: str = DEFAULTS["obsidian_vault"]
    allow_soul_changes: bool = DEFAULTS["allow_soul_changes"]
    model: str | None = DEFAULTS["model"]
    llm: dict[str, Any] = field(default_factory=lambda: dict(DEFAULTS["llm"]))
    forgetting: dict[str, Any] = field(default_factory=lambda: dict(DEFAULTS["forgetting"]))

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Config":
        merged = _deep_merge(DEFAULTS, data or {})
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in merged.items() if k in known})


def default_config_path() -> Path:
    return Path(get_hermes_home()) / "zellandine" / "config.yaml"


def load_config(path: Path | None = None) -> Config:
    """Load config from disk, falling back to defaults."""
    p = path or default_config_path()
    if p and p.exists():
        data = _parse_yaml(p.read_text(encoding="utf-8"))
        return Config.from_dict(data)
    return Config.from_dict({})


def build_provider(cfg: Config) -> DreamProvider:
    """Construct the LLM provider for consolidate/synthesize stages.

    Falls back to the zero-cost offline marker provider if no usable
    credentials are present, so the cycle ALWAYS runs.
    """
    llm = cfg.llm or {}
    provider = (llm.get("provider") or "offline").lower()

    if provider in ("offline", "offline-marker", "", None):
        return OfflineMarkerProvider()

    preset = PROVIDER_PRESETS.get(provider, {})
    base_url = llm.get("base_url") or preset.get("base_url", "")
    api_key_env = llm.get("api_key_env") or preset.get("api_key_env", "")
    model = llm.get("model") or cfg.model or preset.get("model", "")
    api_key = os.environ.get(api_key_env, "") if api_key_env else ""

    if not (base_url and api_key and model):
        # Missing credentials/endpoint — degrade gracefully to offline.
        return OfflineMarkerProvider()

    return OpenAICompatibleProvider(
        base_url=base_url,
        api_key=api_key,
        model=model,
        temperature=float(llm.get("temperature", 0.3)),
        max_tokens=int(llm.get("max_tokens", 4096)),
        timeout=float(llm.get("timeout", 45)),
    )


# --- helpers -------------------------------------------------------------

def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _parse_yaml(text: str) -> dict[str, Any]:
    """Parse config YAML. Uses PyYAML when present, else a minimal parser
    sufficient for this config's shape (scalars + one level of nesting)."""
    try:
        import yaml  # type: ignore

        return yaml.safe_load(text) or {}
    except Exception:
        return _minimal_yaml(text)


def _minimal_yaml(text: str) -> dict[str, Any]:
    root: dict[str, Any] = {}
    current: dict[str, Any] | None = None
    for raw in text.splitlines():
        line = _strip_comment(raw).rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        key, _, val = line.strip().partition(":")
        key = key.strip()
        val = val.strip()
        if indent == 0:
            if val == "":
                current = {}
                root[key] = current
            else:
                root[key] = _coerce(val)
                current = None
        else:
            if current is None:
                current = {}
            current[key] = _coerce(val)
    return root


def _strip_comment(line: str) -> str:
    """Drop a trailing `# comment`, but only when `#` starts a token (at line
    start or preceded by whitespace) — so values like `glm#4` survive."""
    for idx, ch in enumerate(line):
        if ch == "#" and (idx == 0 or line[idx - 1] in " \t"):
            return line[:idx]
    return line


def _coerce(val: str) -> Any:
    if val in ("null", "~", ""):
        return None
    low = val.lower()
    if low in ("true", "yes"):
        return True
    if low in ("false", "no"):
        return False
    if val and (val[0] in "\"'") and val[-1] == val[0]:
        return val[1:-1]
    try:
        return int(val)
    except ValueError:
        pass
    try:
        return float(val)
    except ValueError:
        pass
    return val
