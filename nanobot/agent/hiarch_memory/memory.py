from __future__ import annotations

from typing import Any

from nanobot.agent.hiarch_memory.episodic import EpisodicMemoryStore
from nanobot.agent.hiarch_memory.decision import DecisionMemoryStore
class HiarchMemoryStore:
    _DEFAULT_MAX_HISTORY = 1000

    def __init__(
        self,
        workspace: str,
        episodic_memorystore: EpisodicMemoryStore,
        decision_memorystore: DecisionMemoryStore,
        max_history_entries: int = _DEFAULT_MAX_HISTORY,
    ):
        self.workspace: str = workspace
        self.max_history_entries: int = max_history_entries
        self._episodic_memorystore = episodic_memorystore
        self._decision_memorystore = decision_memorystore

    @staticmethod
    def _format_decision_block(store: DecisionMemoryStore, project: str) -> str:
        decisions = store.list_by_project(project, limit=12)
        if not decisions:
            return ""
        lines: list[str] = []
        for d in decisions:
            reasons = "; ".join(d.reasons) if d.reasons else "—"
            alts = "; ".join(d.alternatives) if d.alternatives else "—"
            lines.append(
                f"- **{d.topic}**: {d.statement}\n"
                f"  - reasons: {reasons}\n"
                f"  - alternatives rejected / not chosen: {alts}\n"
                f"  - importance={d.importance:.2f}, ref={d.source_ref}"
            )
        return "## Recorded decisions (this session)\n\n" + "\n".join(lines)

    async def aggregation_memory(
        self,
        current_message: str,
        memory_project: str | None = None,
    ) -> str:
        parts: list[str] = []
        knowledge: str = await self._episodic_memorystore.retrieve(current_message)
        if knowledge: parts.append(knowledge)
        
        if memory_project:
            block = self._format_decision_block(self._decision_memorystore, memory_project)
            if block: parts.append(block)

        return "\n\n".join(parts) if parts else ""
    
    def efficient(self, memory_project: str | None = None) -> bool:
        if self._episodic_memorystore.can_retrieve():
            return True
        if self._decision_memorystore is not None and memory_project:
            return self._decision_memorystore.has_for_project(memory_project)
        return False