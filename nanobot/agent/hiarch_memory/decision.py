from nanobot.agent.hiarch_memory.base import BaseMemoryStore
from nanobot.agent.hiarch_memory.scheme import EventCandidateResult
from nanobot.providers.openai_compat_provider import OpenAICompatProvider
from nanobot.providers.base import LLMResponse, LLMResponseStructure
from nanobot.utils.prompt_templates import render_template
from nanobot.utils.helpers import format_messages
from typing import List, Dict, Any


class DecisionMemoryStore(BaseMemoryStore):
    def __init__(
            self,
            provider: OpenAICompatProvider,
            model: str,
        ):
        self._provider = provider; self._model = model
    
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
        if isinstance(response, LLMResponse):
            raise Exception('fail to build scheme')
    
    def update(self, history: str): # update internal storage
        ...