from nanobot.agent.hiarch_memory.memory import HiarchMemoryStore
from nanobot.agent.hiarch_memory.shorterm import ShortermMemoryStore
from nanobot.agent.hiarch_memory.episodic import EpisodicMemoryStore
from nanobot.agent.hiarch_memory.decision import DecisionMemoryStore
import jsonlines
from utils.session import Session
from utils.provider import make_provider, MODEL
from typing import List, Dict
import asyncio
import os

WORKSPACE_DIR = 'tests/workspace'
SESSION_DIR = 'tests/workspace/session.jsonl'
BATCH_SIZE: int = 200
MAX_SCORE: float = 0.5


class Memory:
    def __init__(self):
        # create provider
        provider = make_provider()
        # create mem save path
        self._mem_save_path = os.path.join(WORKSPACE_DIR, 'memory')
        if not os.path.exists(self._mem_save_path): os.mkdir(self._mem_save_path)
        
        self.episoidc = EpisodicMemoryStore(workspace=WORKSPACE_DIR, mem_save_path=self._mem_save_path, provider=provider, model=MODEL)
        self.decision = DecisionMemoryStore(workspace=WORKSPACE_DIR, mem_save_path=self._mem_save_path, provider=provider, model=MODEL, batch_size=BATCH_SIZE, max_score=MAX_SCORE)
        self.shorterm = ShortermMemoryStore(workspace=WORKSPACE_DIR, mem_save_path=self._mem_save_path, episodic=self.episoidc, decision=self.decision)
        self.hiarch = HiarchMemoryStore(workspace=WORKSPACE_DIR, episodic=self.episoidc, decision=self.decision)
        self.session = Session(SESSION_DIR)

    async def pipline(self):
        current_message: str = 'Hello'
        history = await self.shorterm.rebuild_history(self.session)
        memory = await self.hiarch.aggregation_memory(current_message)


if __name__ == '__main__':
    memory = Memory()
    asyncio.run(memory.pipline())