"""Read-path router: choose episodic vs decision retrieval for the current user message (Phase 3)."""

from __future__ import annotations

import os
import re
from enum import Enum


class MemorySource(str, Enum):
    EPISODIC = "episodic"
    DECISION = "decision"


def _disabled_routing() -> bool:
    v = os.environ.get("NANOBOT_MEMORY_ROUTE_ALL", "").strip().lower()
    return v in ("1", "true", "yes", "on")


class QueryRouter:
    """Rule-first routing over user text (no extra LLM call)."""

    _DECISION_PATTERNS: tuple[re.Pattern[str], ...] = (
        re.compile(r"决策"),
        re.compile(r"拍板"),
        re.compile(r"(?:已经|早)?定了"),
        re.compile(r"共识"),
        re.compile(r"否决"),
        re.compile(r"为何不"),
        re.compile(r"为什么(?:不|要)(?:用|选|采用)"),
        re.compile(r"上次(?:的)?(?:决定|结论|方案)"),
        re.compile(r"之前的?(?:决定|结论|说法)"),
        re.compile(r"(?:方案|技术)\s*(?:选型|敲定)"),
        re.compile(r"\bdecisions?\b", re.I),
        re.compile(r"\bwhy\s+did\s+we\b", re.I),
        re.compile(r"\bagreed\b", re.I),
        re.compile(r"\bsupersed(?:e|ed)\b", re.I),
    )

    _DEADLINE_PATTERNS: tuple[re.Pattern[str], ...] = (
        re.compile(r"deadline", re.I),
        re.compile(r"\bddl\b", re.I),
        re.compile(r"截止(?:日|时间)?"),
        re.compile(r"上线(?:日|日期|时间)?"),
        re.compile(r"交付日"),
        re.compile(r"时间节点"),
        re.compile(r"哪天(?:上|交付|发布)"),
        re.compile(r"milestone", re.I),
    )

    _HISTORY_PATTERNS: tuple[re.Pattern[str], ...] = (
        re.compile(r"上周"),
        re.compile(r"上个月"),
        re.compile(r"当时"),
        re.compile(r"发生过(?:什么)?"),
        re.compile(r"会议纪要"),
        re.compile(r"纪要"),
        re.compile(r"回忆(?:一下)?"),
        re.compile(r"上次会议"),
        re.compile(r"那段(?:时间|讨论)"),
        re.compile(r"\bwhat\s+happened\b", re.I),
        re.compile(r"\blast\s+(?:week|meeting)\b", re.I),
        re.compile(r"\bremind\s+me\b", re.I),
    )

    @staticmethod
    def _any_match(text: str, patterns: tuple[re.Pattern[str], ...]) -> bool:
        return any(p.search(text) for p in patterns)

    def route(self, message: str) -> list[MemorySource]:
        """
        Return ordered memory sources to query.

        Precedence: decision-related → deadline-only decision → history-only episodic → default episodic.
        When ``NANOBOT_MEMORY_ROUTE_ALL`` is truthy, always query both layers (escape hatch).
        """
        if _disabled_routing():
            return [MemorySource.DECISION, MemorySource.EPISODIC]

        raw = (message or "").strip()
        if not raw:
            return [MemorySource.EPISODIC]

        if self._any_match(raw, self._DECISION_PATTERNS):
            return [MemorySource.DECISION, MemorySource.EPISODIC]
        if self._any_match(raw, self._DEADLINE_PATTERNS):
            return [MemorySource.DECISION]
        if self._any_match(raw, self._HISTORY_PATTERNS):
            return [MemorySource.EPISODIC]
        return [MemorySource.EPISODIC]
