from __future__ import annotations

from typing import Any

from nanobot.agent.hiarch_memory.episodic import EpisodicMemoryStore
from nanobot.agent.hiarch_memory.decision import DecisionMemoryStore
class HiarchMemoryStore:
    _DEFAULT_MAX_HISTORY = 1000

    def __init__(
        self,
        workspace: str,
        episodic: EpisodicMemoryStore,
        decision: DecisionMemoryStore,
        max_history_entries: int = _DEFAULT_MAX_HISTORY,
    ):
        self.workspace: str = workspace
        self.max_history_entries: int = max_history_entries
        self._episodic = episodic
        self._decision = decision

    async def aggregation_memory(
        self,
        current_message: str,
    ) -> str:
        parts: list[str] = []
        knowledge: str = await self._episodic.retrieve(current_message)
        if knowledge.strip():
            parts.append(f"## Episodic knowledge\n\n{knowledge.strip()}")

        if self._decision is not None:
            dec_block = self._decision.prompt_block_for_query(current_message)
            if dec_block:
                parts.append(dec_block)

        return "\n\n".join(parts) if parts else ""

    def efficient(self, memory_project: str | None = None) -> bool:
        _ = memory_project  # reserved for per-project decision scopes (future schema)
        if self._episodic.can_retrieve():
            return True
        if self._decision is not None and self._decision.has_any_candidates():
            return True
        return False