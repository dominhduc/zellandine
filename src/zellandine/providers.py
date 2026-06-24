"""LLM provider abstraction.

Supports three modes:
1. offline-marker — scans for literal `DREAM:` markers, no API cost
2. openai-compatible — calls any OpenAI-compatible endpoint (zai, OpenRouter, etc.)
3. (future) ollama — local model
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any, Protocol


class ProviderError(RuntimeError):
    pass


class DreamProvider(Protocol):
    name: str

    def consolidate(self, episodes_text: str, context: str) -> str:
        """Stage 2: episodes → LLM analysis (JSON proposals text)."""
        raise NotImplementedError

    def synthesize(self, episodes_text: str, proposals_text: str) -> str:
        """Stage 4: cross-session pattern detection (JSON insights text)."""
        raise NotImplementedError


# --- Offline Marker Provider ---

MARKER_RE = re.compile(
    r"^\s*(?:-\s*)?DREAM:\s*(memory|user|skill|fact)\s*:\s*(.+?)\s*$",
    re.IGNORECASE,
)


class OfflineMarkerProvider:
    """Scans for literal DREAM: markers in text. Zero API cost."""

    name = "offline-marker"

    def consolidate(self, episodes_text: str, context: str) -> str:
        proposals = []
        for i, line in enumerate(episodes_text.splitlines(), 1):
            match = MARKER_RE.match(line)
            if match:
                kind, payload = match.groups()
                proposals.append({
                    "id": f"dream-{i:03d}",
                    "target": kind if kind in ("memory", "user", "skill") else "memory",
                    "action": "add",
                    "content": payload.strip(),
                    "reason": f"Explicit DREAM marker at line {i}",
                    "confidence": 1.0,
                    "risk": "low",
                    "priority": "normal",
                    "provenance": f"marker:{i}",
                })
        return json.dumps(proposals, ensure_ascii=False, indent=2)

    def synthesize(self, episodes_text: str, proposals_text: str) -> str:
        return "[]"


# --- OpenAI-Compatible Provider ---

class OpenAICompatibleProvider:
    """Calls any OpenAI-compatible chat completions endpoint."""

    name = "openai-compatible"

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

    def _call(self, system_prompt: str, user_prompt: str) -> str:
        """Make a single chat completion call."""
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        data = json.dumps(payload).encode("utf-8")

        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                return body["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as exc:
            raise ProviderError(f"LLM API returned {exc.code}: {exc.reason}") from exc
        except Exception as exc:
            raise ProviderError(f"LLM call failed: {exc}") from exc

    def consolidate(self, episodes_text: str, context: str) -> str:
        system = (
            "You are a memory consolidation engine. Analyze the following "
            "session episodes and current memory state. Output a JSON array of "
            "proposals for memory, user profile, or skill changes. "
            "Each proposal needs: id, target (memory|user|skill), action "
            "(add|replace|remove|patch), content, reason, confidence (0-1), "
            "risk (low|medium|high), priority (low|normal|high). "
            "Maximum 5 proposals. Be conservative — only propose what you're confident about."
        )
        user = f"## Current state\n{context}\n\n## Episodes\n{episodes_text}\n\n## Proposals (JSON):"
        return self._call(system, user)

    def synthesize(self, episodes_text: str, proposals_text: str) -> str:
        system = (
            "You are a REM-sleep synthesis engine. Look across the episodes and "
            "proposals for non-obvious patterns, recurring themes, behavioural drift, "
            "and novel connections. Output a JSON array of insights. "
            "Each insight needs: type (pattern|connection|suggestion|drift_alert), "
            "content, evidence, confidence (0-1). "
            "Maximum 3 insights. Be speculative but grounded in evidence."
        )
        user = (
            f"## Episodes\n{episodes_text}\n\n## Proposals\n{proposals_text}\n\n## Insights (JSON):"
        )
        # Higher temperature for REM
        old_temp = self.temperature
        self.temperature = 0.6
        try:
            return self._call(system, user)
        finally:
            self.temperature = old_temp
