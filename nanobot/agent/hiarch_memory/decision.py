from nanobot.agent.hiarch_memory.base import BaseMemoryStore
from nanobot.agent.hiarch_memory.scheme import EventCandidate, EventCandidateResult
from nanobot.providers.openai_compat_provider import OpenAICompatProvider
from nanobot.providers.base import LLMResponse, LLMResponseStructure
from nanobot.utils.prompt_templates import render_template
from nanobot.utils.helpers import write_jsonlines, read_jsonlines
from typing import List, Dict, Tuple, Any
import os

class DecisionMemoryStore(BaseMemoryStore):
    def __init__(
            self,
            workspace: str,
            mem_save_path: str,
            provider: OpenAICompatProvider,
            model: str,
        ):
        self._workspace = workspace; self._mem_save_path = mem_save_path
        self._provider = provider; self._model = model
        self._ec_save_path = os.path.join(self._mem_save_path, '.ec.jsonl')
    
    async def extract(self, history: List[Dict[str, Any]]) -> str:
        # extract event candidates from window
        histext: str = self._format_messages(history)
        msg: List[Dict[str, Any]] = [
            {'role': 'system', 'content': render_template('custom/extract.md', strip=True)},
            {'role': 'user', 'content': histext},
        ]
        _scheme = EventCandidateResult
        self._provider.set_scheme(_scheme)
        response = await self._provider.chat_scheme(msg, model=self._model, tools=None, tool_choice=None)
        if isinstance(response, LLMResponse): raise Exception('fail to build scheme')
        
        # cluster ec
        parsed: Dict[str, List] = response.parsed
        result = parsed.get('result')
        database: List[Dict] | None = read_jsonlines(self._ec_save_path)
        if not database: # if first
            write_jsonlines(result, self._ec_save_path)
        else:
            for ec in result:
                result_retrieved: List[Dict] = self._retrieve(ec, database)
                result_merged: List[Dict] = self._merge(ec, result_retrieved)
                
                
    
    def _merge(self, ec: Dict, result: List[Dict]) -> List[Dict]:
        ...
                
    def _retrieve(self, query: Dict, database: List[Dict]) -> List[Tuple[int, Dict]]: # top-k
        return 

    def _init_ec_save_path(self):
        with open(self._ec_save_path, mode='w') as writer:
            writer.write('')

    def _convert_eventcandidate(self, ec: Dict[str, Any]) -> EventCandidate:
        return EventCandidate(**ec)