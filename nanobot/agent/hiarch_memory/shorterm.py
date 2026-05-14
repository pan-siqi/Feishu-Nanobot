
from nanobot.session.manager import Session
from nanobot.agent.hiarch_memory.episodic import EpisodicMemoryStore
from nanobot.agent.hiarch_memory.decision import DecisionMemoryStore
from nanobot.agent.hiarch_memory.router import Router
from nanobot.agent.hiarch_memory.metaclass import FileName
from nanobot.utils.helpers import write_jsonlines, write_file, read_file
from typing import Any, Dict, List, Callable
import asyncio
import jsonlines
import os

class ShortermMemoryStore:
    def __init__(
        self,
        workspace: str,
        mem_save_path: str,
        episodic: EpisodicMemoryStore,
        decision: Any | None = None,
    ):
        self._workspace = workspace
        self._mem_save_path = mem_save_path
        self._max_history_num: int = 5
        self._buffer: List = list()
        self._episodic = episodic
        self._decision = decision
        self._router = Router(
            self._mem_save_path,
            self._episodic,
            self._decision,
        )
    
    async def rebuild_history(self, session: Session): # make number of history come into [m/2, m]
        # split different project into different space
        project_id: str = session.key; project_id = project_id.replace(':', '_')
        _project_path: str = os.path.join(self._mem_save_path, project_id)
        if not os.path.exists(_project_path): os.mkdir(_project_path)

        # read file path in project
        _cursor_path: str = os.path.join(_project_path, FileName.cursor)
        _history_path: str = os.path.join(_project_path, FileName.history)
        _shortermem_path: str = os.path.join(_project_path, FileName.shortermem)
        _cursor: int = int(read_file(_cursor_path)) if os.path.exists(_cursor_path) else 0
        
        history: List[Dict[str, Any]] = session.get_history(max_messages=0, clip_index=_cursor)
        
        # if should rebuild
        if self._is_rebuild(history):
            _num: int = self._get_num(history, _cursor, _cursor_path)
            batch = history[0:_num]
            write_jsonlines(batch, _history_path)

            # <operate batch>
            # await self._router.operate_batch(session=session, project=session.key)
            asyncio.create_task(self._router.operate_batch(session=session, project_id=project_id))
            history = history[_num:]
        
        # save total shortermem
        write_jsonlines(history, _shortermem_path)
        return history
    
    def _build_path(self, project_id: str, file_name: str) -> str:
        return os.path.join(self._mem_save_path, project_id, file_name)

    def _is_rebuild(self, history: List) -> bool:
        return len(history) >= self._max_history_num

    def _get_num(self, history: List, _cursor: int, _cursor_path: str) -> int:
        _num = len(history) - self._max_history_num // 2
        _cursor += _num; write_file(str(_cursor), _cursor_path)
        return _num
