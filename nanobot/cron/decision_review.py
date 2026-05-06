"""Decision review reminder helpers.

Full decay / review queue depends on Decision schema fields not yet on EventCandidate.
Import-safe stub until Phase 4 wiring.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from nanobot.agent.hiarch_memory.decision import DecisionMemoryStore


@dataclass
class DecisionReviewRequest:
    project: str
    limit: int = 3


class DecisionReviewService:
    """Placeholder: ``DecisionMemoryStore`` has no decay/list_review_candidates yet."""

    def __init__(self, decision_store: Any):
        self._store = decision_store

    def build_review_message(self, request: DecisionReviewRequest) -> str:
        _ = self._store
        _ = request
        return ""
