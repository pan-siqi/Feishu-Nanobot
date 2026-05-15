from __future__ import annotations

from loguru import logger

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

    async def aggregation_memory(self, current_message: str, project_id: str) -> str:
        parts: str = ''
        # Module1: Retrieve from Episodic
        knowledge = await self._episodic.retrieve(current_message, project_id)
        if knowledge: parts += f"## Episodic knowledge\n\n{knowledge.strip()}"
        return parts

    def efficient(self, memory_project: str | None = None) -> bool:
        if self._episodic.can_retrieve():
            return True
        if self._decision is None:
            return False
        if memory_project:
            return self._decision.has_any_candidates(project=memory_project)
        return self._decision.has_any_candidates()
