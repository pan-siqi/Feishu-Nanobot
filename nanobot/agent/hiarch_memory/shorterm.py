from typing import Any, Dict, List

import jsonlines
import os
from loguru import logger
from nanobot.session.manager import Session
from nanobot.agent.hiarch_memory.episodic import EpisodicMemoryStore


class ShortermMemoryStore:
    def __init__(
        self,
        workspace: str,
        episodic_memorystore: EpisodicMemoryStore,
        decision_store: Any | None = None,
    ):
        self._workspace = workspace
        self._mem_save_path = os.path.join(self._workspace, 'memory')
        if not os.path.exists(self._mem_save_path):
            os.mkdir(self._mem_save_path)
        self._save_path = os.path.join(self._mem_save_path, '.history.jsonl')
        self._cursor_save_path = os.path.join(self._mem_save_path, '.cursor')
        self._shorterm_memory_save_path = os.path.join(self._mem_save_path, '.shortermem.jsonl')
        self._max_history_num: int = 1000
        self._cursor: int = self._load_cursor() if os.path.exists(self._cursor_save_path) else 0
        self._buffer: List = list()
        self._episodic_memorystore = episodic_memorystore
        self._decision_store = decision_store
    
    async def rebuild_history(self, session: Session): # make number of history come into [m/2, m]
        history: List[Dict[str, Any]] = session.get_history(max_messages=0, clip_index=self._cursor)
        
        # if should rebuild
        if self._is_rebuild(history):
            _num: int = self._get_num(history)
            batch = history[0:_num]
            self._save_history(batch)
            try:
                if self._decision_store is not None and batch:
                    extracted = await self._decision_store.extract(batch, project=session.key)
                    if extracted:
                        await self._decision_store.store(extracted)
            except Exception:
                logger.exception("Decision extract/store failed for session {}", session.key)
            history = history[_num:]

        # if should build-document
        if os.path.exists(self._save_path) and self._load_history():
            await self._episodic_memorystore.check()

        self._cleanup_history()
        
        # save total shortermem
        self._save_shorterm_memory(history)
        return history

    def _is_rebuild(self, history: List) -> bool:
        return len(history) >= self._max_history_num
        # return False

    def _get_num(self, history: List) -> int:
        _num = len(history) - self._max_history_num // 2
        self._cursor += _num; self._save_cursor()
        return _num
    
    def _save_shorterm_memory(self, shortermem: List[Dict[str, Any]]):
        with jsonlines.open(self._shorterm_memory_save_path, mode='w') as writer:
            writer.write_all(shortermem)

    def _cleanup_history(self):
        if os.path.exists(self._save_path): os.remove(self._save_path)
    
    def _load_history(self) -> List[Dict[str, Any]]:
        _records = []
        with jsonlines.open(self._save_path, mode='r') as reader:
            for obj in reader:
                _records.append(obj)
        return _records

    def _save_history(self, history: List):
        with jsonlines.open(self._save_path, mode='a') as writer:
            writer.write_all(history)
    
    def _save_cursor(self):
        with open(self._cursor_save_path, mode='w', encoding='utf-8') as writer:
            writer.write(str(self._cursor))
    
    def _load_cursor(self) -> int:
        with open(self._cursor_save_path, mode='r', encoding='utf-8') as reader:
            content = reader.read().strip()
        try:
            content = int(content)
        except Exception as e:
            content = 0
            print(f'extract clip index fail from `{self._cursor_save_path}`!')
        return content