from __future__ import annotations

from loguru import logger

from nanobot.agent.hiarch_memory.episodic import EpisodicMemoryStore
from nanobot.agent.hiarch_memory.decision import DecisionMemoryStore
from nanobot.agent.hiarch_memory.query_router import MemorySource, QueryRouter


class HiarchMemoryStore:
    _DEFAULT_MAX_HISTORY = 1000

    def __init__(
        self,
        workspace: str,
        episodic: EpisodicMemoryStore,
        decision: DecisionMemoryStore,
        max_history_entries: int = _DEFAULT_MAX_HISTORY,
        query_router: QueryRouter | None = None,
    ):
        self.workspace: str = workspace
        self.max_history_entries: int = max_history_entries
        self._episodic = episodic
        self._decision = decision
        self._query_router = query_router or QueryRouter()

    async def aggregation_memory(
        self,
        current_message: str,
        memory_project: str | None = None,
        *,
        sources: list[MemorySource] | None = None,
    ) -> str:
        route = sources if sources is not None else self._query_router.route(current_message)
        active = list(dict.fromkeys(route))

        decision_part = ""
        episodic_part = ""

        if MemorySource.DECISION in active and self._decision is not None:
            decision_part = self._decision.prompt_block_for_query(
                current_message, project=memory_project
            )

        if MemorySource.EPISODIC in active:
            knowledge = await self._episodic.retrieve(current_message)
            if knowledge.strip():
                episodic_part = f"## Episodic knowledge\n\n{knowledge.strip()}"

        parts: list[str] = []
        if decision_part:
            parts.append(decision_part)
        if episodic_part:
            parts.append(episodic_part)

        logger.debug(
            "aggregation_memory route={} project={} has_decision_block={} has_episodic_block={}",
            [s.value for s in active],
            memory_project,
            bool(decision_part),
            bool(episodic_part),
        )

        return "\n\n".join(parts) if parts else ""

    def efficient(self, memory_project: str | None = None) -> bool:
        if self._episodic.can_retrieve():
            return True
        if self._decision is None:
            return False
        if memory_project:
            return self._decision.has_any_candidates(project=memory_project)
        return self._decision.has_any_candidates()
