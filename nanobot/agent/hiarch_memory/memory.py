from nanobot.agent.hiarch_memory.shorterm import ShortermMemoryStore
from nanobot.agent.hiarch_memory.semantic import SemanticMemoryStore
from nanobot.agent.hiarch_memory.working import WorkingMemoryStore
from nanobot.agent.hiarch_memory.episodic import EpisodicMemoryStore
from typing import List, Dict, Optional

class HiarchMemoryStore:
    _DEFAULT_MAX_HISTORY = 1000
    def __init__(
            self,
            workspace: str,
            episodic_memorystore: EpisodicMemoryStore,
            max_history_entries: int = _DEFAULT_MAX_HISTORY):
        self.workspace: str = workspace
        self.max_history_entries: int = max_history_entries
        self._episodic_memorystore = episodic_memorystore

    async def aggregation_memory(self, current_message: str) -> str:
        # Add Router
        mem: str = ''
        # First: Retrieve Knowledge
        kwg: str = await self._episodic_memorystore.retrieve(current_message)
        print(kwg)
        if kwg: mem += kwg
        return mem
    
    def efficient(self) -> bool:
        return self._episodic_memorystore.can_retrieve()