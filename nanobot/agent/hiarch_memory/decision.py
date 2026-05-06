from nanobot.agent.hiarch_memory.base import BaseMemoryStore
from nanobot.agent.hiarch_memory.scheme import EventCandidate, EventCandidateResult, EventCandidateMergeResult
from nanobot.agent.hiarch_memory.database.ec_database import EventCandidateMetaClass, EventCandidateRepository
from nanobot.providers.openai_compat_provider import OpenAICompatProvider
from nanobot.providers.base import LLMResponse, LLMResponseStructure
from nanobot.utils.prompt_templates import render_template
from nanobot.utils.helpers import format_messages
from sqlalchemy.orm.session import Session
from typing import List, Dict, Tuple, Any
from uuid import uuid4
from datetime import datetime
import os


def _merge_eval_bool(content: str | None) -> bool:
    """Parse evaluate.md LLM output as merge-or-not (never use eval())."""
    if not content:
        return False
    t = content.strip().lower()
    if t in ("true", "yes", "1", "是", "y"):
        return True
    if t in ("false", "no", "0", "否", "n"):
        return False
    head = t.split()[0] if t else ""
    return head in ("true", "yes", "1", "是")


class DecisionMemoryStore(BaseMemoryStore):
    def __init__(
            self,
            workspace: str,
            mem_save_path: str,
            provider: OpenAICompatProvider,
            model: str,
            database_session: Session,
            repo: EventCandidateRepository,
        ):
        self._workspace = workspace; self._mem_save_path = mem_save_path
        self._provider = provider; self._model = model
        self._session = database_session
        self._ec_repo = repo
        self._ec_save_path = os.path.join(self._mem_save_path, '.ec.jsonl')

    def has_any_candidates(self) -> bool:
        return bool(self._ec_repo.list(limit=1))

    def prompt_block_for_query(self, query: str, top_k: int = 3) -> str:
        """Canonical text blocks for top matching event candidates (system prompt)."""
        hits = self._ec_repo.retrieve(query, top_k=top_k)
        if not hits:
            return ""
        chunks = [self._ec_repo.convert_text(ec) for ec, _ in hits]
        return "## Related decisions\n\n" + "\n\n".join(chunks)
    
    async def extract(self, history: List[Dict[str, Any]]) -> List[str]:
        # extract event candidates from window
        histext: str = format_messages(history)
        msg: List[Dict[str, Any]] = [
            {'role': 'system', 'content': render_template('custom/decision_extract.md', strip=True)},
            {'role': 'user', 'content': histext},
        ]
        _scheme = EventCandidateResult
        self._provider.set_scheme(_scheme)
        response = await self._provider.chat_scheme(msg, model=self._model, tools=None, tool_choice=None)
        if isinstance(response, LLMResponse): raise Exception('fail to build scheme')
        
        # merge ec
        parsed: Dict[str, List] = response.parsed
        result: List[Dict] = parsed.get('result')
        _evidence_message_ids: List[str] = list()
        for item in result: _evidence_message_ids.extend(item.get('evidence_message_ids'))
        
        if not self._ec_repo.list(): # if first
            for item in result: self._ec_repo.create(self._scheme_to_metaclass(item))
        else:
            for item in result:
                ec = self._scheme_to_metaclass(item)
                restr = self._ec_repo.retrieve(ec)
                is_create: bool = True
                if restr:
                    ec_merge = await self._merge(ec, restr)
                    if ec_merge: self._ec_repo.update_by_ec_id(ec_merge); is_create = False
                if is_create: self._ec_repo.create(ec)
        self._ec_repo.build_embed()
        return _evidence_message_ids
                
    async def _merge(self, ec: EventCandidateMetaClass, result: List[Tuple[EventCandidateMetaClass, float]]) -> EventCandidateMetaClass | None:
        ec_text = self._ec_repo.convert_text(ec, remove_ec_id=True)
        ecs_text = ''
        for res in result: 
            ecs_text += self._ec_repo.convert_text(res[0]).strip() + '\n\n'
        
        msg_eval: List[Dict[str, Any]] = [
            {'role': 'user', 'content': render_template('custom/evaluate.md', strip=True, event=ec_text, event_list=ecs_text)},
        ]
        response_eval = await self._provider.chat_with_retry(msg_eval, model=self._model, tools=None, tool_choice=None)
        
        if not _merge_eval_bool(response_eval.content):
            return None

        msg_merge: List[Dict[str, Any]] = [
            {'role': 'user', 'content': render_template('custom/merge.md', strip=True, event=ec_text, event_list=ecs_text)},
        ]
        _scheme = EventCandidateMergeResult
        self._provider.set_scheme(_scheme)
        response_merge = await self._provider.chat_scheme(msg_merge, model=self._model, tools=None, tool_choice=None)
        if isinstance(response_merge, LLMResponse): raise Exception('fail to build scheme')
        
        # execute merge process
        parsed: Dict[str, Any] = response_merge.parsed # ec_id, EventCandidate
        return self._scheme_to_metaclass(parsed.get('event_candidate'), parsed.get('ec_id'))
    
    def _scheme_to_metaclass(self, item: Dict, ec_id: str | None = None) -> EventCandidateMetaClass:
        if not ec_id: ec_id = f'ec_{uuid4().hex[:10]}'
        ec = EventCandidateMetaClass(ec_id=ec_id, aliases=[], update_at=datetime.now().isoformat(), **item)
        return ec

    def _init_ec_save_path(self):
        with open(self._ec_save_path, mode='w') as writer:
            writer.write('')

    def _convert_eventcandidate(self, ec: Dict[str, Any]) -> EventCandidate:
        return EventCandidate(**ec)
