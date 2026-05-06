from nanobot.agent.hiarch_memory.memory import HiarchMemoryStore
from nanobot.agent.hiarch_memory.shorterm import ShortermMemoryStore
from nanobot.agent.hiarch_memory.episodic import EpisodicMemoryStore
from nanobot.agent.hiarch_memory.decision import DecisionMemoryStore
from nanobot.agent.hiarch_memory.database.ec_database import Session as DataBaseSession
from nanobot.agent.hiarch_memory.database.ec_database import connect_database, EventCandidateMetaClass, EventCandidateRepository
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
MODEL = 'gpt-4o-mini'

class Memory:
    def __init__(self):
        # create provider
        provider = make_provider()
        # create mem save path
        self._mem_save_path = os.path.join(WORKSPACE_DIR, 'memory')
        if not os.path.exists(self._mem_save_path): os.mkdir(self._mem_save_path)
        self.session = Session(SESSION_DIR)
        _SessionLocal = connect_database() # create session
        self._database_session: DataBaseSession = _SessionLocal()
        self._repo = EventCandidateRepository(self._database_session, BATCH_SIZE, MAX_SCORE)

        
        self.episodic = EpisodicMemoryStore(
            workspace=WORKSPACE_DIR,
            mem_save_path=self._mem_save_path,
            provider=provider,
            model=MODEL,
        )
        self.decision = DecisionMemoryStore(
            workspace=WORKSPACE_DIR,
            mem_save_path=self._mem_save_path,
            provider=provider,
            model=MODEL,
            database_session=self.session,
            repo=self._repo,
        )
        self.shorterm = ShortermMemoryStore(
            workspace=WORKSPACE_DIR,
            mem_save_path=self._mem_save_path,
            episodic=self.episodic,
            decision=self.decision,
        )
        # self.hiarch = HiarchMemoryStore(workspace=WORKSPACE_DIR, episodic=self.episoidc, decision=self.decision)

    async def pipline(self):
        current_message: str = 'Hello'
        history = await self.shorterm.rebuild_history(self.session)
        # memory = await self.hiarch.aggregation_memory(current_message)


if __name__ == '__main__':
    memory = Memory()
    asyncio.run(memory.pipline())