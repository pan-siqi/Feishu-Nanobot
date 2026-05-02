from nanobot.agent.hiarch_memory.memory import HiarchMemoryStore
from nanobot.agent.hiarch_memory.shorterm import ShortermMemoryStore
from nanobot.agent.hiarch_memory.episodic import EpisodicMemoryStore
from nanobot.agent.hiarch_memory.decision import DecisionMemoryStore
import jsonlines
from utils.session import Session
from utils.provider import make_provider, MODEL
from typing import List, Dict
import asyncio

WORKSPACE_DIR = 'tests/workspace'
SESSION_DIR = 'tests/workspace/session.jsonl'

class Memory:
    def __init__(self):
        provider = make_provider()
        self.episoidc = EpisodicMemoryStore(workspace=WORKSPACE_DIR, provider=provider, model=MODEL)
        self.decision = DecisionMemoryStore(workspace=WORKSPACE_DIR, provider=provider, model=MODEL)
        self.shorterm = ShortermMemoryStore(workspace=WORKSPACE_DIR, episodic=self.episoidc, decision=self.decision)
        self.hiarch = HiarchMemoryStore(workspace=WORKSPACE_DIR, episodic=self.episoidc, decision=self.decision)
        self.session = Session(SESSION_DIR)

    async def pipline(self):
        current_message: str = 'Hello'
        history = await self.shorterm.rebuild_history(self.session)
        memory = await self.hiarch.aggregation_memory(current_message)


if __name__ == '__main__':
    memory = Memory()
    asyncio.run(memory.pipline())