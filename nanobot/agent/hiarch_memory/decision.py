from __future__ import annotations
from nanobot.agent.hiarch_memory.base import BaseMemoryStore
from nanobot.agent.hiarch_memory.database import EventCandidateMetaClass, EventCandidateRepository, item_row_to_meta
from nanobot.agent.hiarch_memory.scheme import DecisionStatus, EventCandidate, EventCandidateMergeResult, EventCandidateResult
from nanobot.providers.base import LLMResponse
from nanobot.providers.openai_compat_provider import OpenAICompatProvider
from nanobot.utils.helpers import format_messages
from nanobot.utils.prompt_templates import render_template
from sqlalchemy.orm.session import Session
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple
from uuid import uuid4
from loguru import logger
import os

def _merge_eval_bool(content: str | None) -> bool:
    if not content:
        return False
    t = content.strip().lower()
    if t in ("true", "yes", "1", "是", "y"):
        return True
    if t in ("false", "no", "0", "否", "n"):
        return False
    head = t.split()[0] if t else ""
    return head in ("true", "yes", "1", "是")

_ACTIVE_MIN_CONF  = 0.65
_REINFORCE_FACTOR = 1.8
_STRENGTH_CAP     = 50

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
        self._workspace = workspace
        self._mem_save_path = mem_save_path
        self._provider = provider
        self._model = model
        self._session = database_session
        self._ec_repo = repo
        self._ec_save_path = os.path.join(self._mem_save_path, ".ec.jsonl")
    
    def has_any_candidates(self, project: str | None = None) -> bool:
        return bool(self._ec_repo.list(limit=1, project=project))
    
    def prompt_block_for_query(self, query: str, top_k: int = 3, project: str | None = None) -> str:
        hits = self._ec_repo.retrieve(query, top_k=top_k, project=project)
        if not hits: return ''
        chunks = [self._ec_repo.convert_text(ec) for ec, _ in hits]
        return '## Related decisions\n\n{}'.format('\n\n'.join(chunks))

    def decay(self) -> int:
        return self._ec_repo.apply_decay()

    def list_review_candidates(self, project: str, limit: int = 3) -> list[EventCandidateMetaClass]:
        return self._ec_repo.list_review_candidates(project=project, limit=limit)

    def mark_review(self, ec_id: str, action: str, new_statement: str | None = None) -> EventCandidateMetaClass | None:
        row = self._ec_repo.get_by_ec_id(ec_id)
        if row is None:
            return None
        meta = item_row_to_meta(row)
        now_iso = datetime.now(timezone.utc).isoformat()
        act = (action or "").strip().lower()

        if act == 'reinforce':
            meta.strength = min(_STRENGTH_CAP, float(meta.strength or 1.0) * _REINFORCE_FACTOR)
            meta.review_count = int(meta.review_count or 0) + 1
            meta.last_reviewed_at = now_iso
            meta.update_at = now_iso
            self._ec_repo.update_by_ec_id(meta)
            refreshed = self._ec_repo.get_by_ec_id(ec_id)
            return item_row_to_meta(refreshed) if refreshed else None

        if act == 'expire':
            meta.status = DecisionStatus.EXPIRED.value
            meta.last_reviewed_at = now_iso
            meta.update_at = now_iso
            self._ec_repo.update_by_ec_id(meta)
            refreshed = self._ec_repo.get_by_ec_id(ec_id)
            return item_row_to_meta(refreshed) if refreshed else None

        if act == 'update':
            stmt = (new_statement or "").strip()
            if not stmt:
                return None
            old = meta
            old.status = DecisionStatus.SUPERSEDED.value
            old.last_reviewed_at = now_iso
            old.update_at = now_iso
            self._ec_repo.update_by_ec_id(old)

            new_id = f"ec_{uuid4().hex[:10]}"
            new_meta = EventCandidateMetaClass(
                ec_id                =  new_id,
                event_name           =  old.event_name,
                aliases              =  list(old.aliases),
                decision_signal      =  old.decision_signal,
                summary              =  old.summary,
                decision_result      =  stmt,
                entities             =  list(old.entities),
                evidence_message_ids =  list(old.evidence_message_ids),
                confidence           =  min(1.0, float(old.confidence) + 0.05),
                update_at            =  now_iso,
                project              =  old.project,
                reasons              =  list(old.reasons),
                objections           =  list(old.objections),
                alternatives         =  list(old.alternatives),
                deadline             =  old.deadline,
                participants         =  list(old.participants),
                importance           =  float(old.importance),
                strength             =  min(_STRENGTH_CAP, float(old.strength or 1.0) * 1.2),
                last_reviewed_at     =  now_iso,
                review_count         =  int(old.review_count or 0) + 1,
                status               =  DecisionStatus.ACTIVE.value,
                supersedes           =  old.ec_id,
            )
            self._ec_repo.create(new_meta)
            self._ec_repo.build_embed()
            refreshed = self._ec_repo.get_by_ec_id(new_id)
            return item_row_to_meta(refreshed) if refreshed else None
        return None
    
    async def extract(self, history: List[Dict[str, Any]], project_id: str) -> List[str]:
        histext: str = format_messages(history)
        msg: List[Dict[str, Any]] = [
            {"role": "system", "content": render_template("custom/decision_extract.md", strip=True)},
            {"role": "user", "content": histext},
        ]
        self._provider.set_scheme(EventCandidateResult)
        response = await self._provider.chat_scheme(msg, model=self._model, tools=None, tool_choice=None)
        if isinstance(response, LLMResponse):
            raise Exception("fail to build scheme")

        parsed: Dict[str, Any] = response.parsed or {}
        result: List[Dict[str, Any]] = list(parsed.get('result') or [])
        _evidence_message_ids: List[str] = []
        for item in result:
            ev = item.get('evidence_message_ids') or []
            _evidence_message_ids.extend(ev)

        if not self._ec_repo.list(project_id=project_id, limit=1): # first
            for item in result:
                ec: EventCandidateMetaClass = self._scheme_to_metaclass(item, project_id)
                self._ec_repo.create(ec)
        else:
            for item in result:
                ec: EventCandidateMetaClass = self._scheme_to_metaclass(item, project_id)
                retrsult = self._ec_repo.retrieve(ec, project_id)
                is_create: bool = True
                if retrsult: # if have retrieve result
                    ec_merge = await self._merge(ec, project_id, retrsult)
                    if ec_merge:
                        self._ec_repo.update_by_ec_id(ec_merge)
                        is_create = False
                if is_create:
                    self._ec_repo.create(ec)
        self._ec_repo.build_embed()
        return _evidence_message_ids

    async def _merge(
        self,
        ec: EventCandidateMetaClass,
        project_id: str,
        retrsult: List[Tuple[EventCandidateMetaClass, float]],
    ) -> EventCandidateMetaClass | None:
        # merge with top-k similary items
        ec_text = self._ec_repo.convert_text(ec, remove_ec_id=True)
        ecs_text = ''
        for res in retrsult: ecs_text += self._ec_repo.convert_text(res[0]).strip() + "\n\n"
        
        # first step: evaluate whether merge
        msg_eval: List[Dict[str, Any]] = [
            {"role": "user", "content": render_template("custom/evaluate.md", strip=True, event=ec_text, event_list=ecs_text)},
        ]
        response_eval = await self._provider.chat_with_retry(
            msg_eval, model=self._model, tools=None, tool_choice=None
        )
        if not _merge_eval_bool(response_eval.content): return None

        # second step: evaluate whether merge
        msg_merge: List[Dict[str, Any]] = [
            {"role": "user", "content": render_template("custom/merge.md", strip=True, event=ec_text, event_list=ecs_text)},
        ]
        self._provider.set_scheme(EventCandidateMergeResult)
        response_merge = await self._provider.chat_scheme(msg_merge, model=self._model, tools=None, tool_choice=None)
        if isinstance(response_merge, LLMResponse): raise Exception("fail to build scheme")

        parsed: Dict[str, Any] = response_merge.parsed
        ec: EventCandidateMetaClass = parsed.get('event_candidate')
        return self._scheme_to_metaclass(
            item       = ec,
            project_id = project_id,
            ec_id      = parsed.get('ec_id'),
        )

    def _scheme_to_metaclass(
        self,
        item: Dict[str, Any],
        project_id: str,
        ec_id: str | None = None,
    ) -> EventCandidateMetaClass:
        if not ec_id: ec_id = f"ec_{uuid4().hex[:10]}"
        now_iso = datetime.now().isoformat()
        confidence = float(item.get('confidence', 0.0))
        importance = float(item.get('importance', confidence)); importance = max(0.0, min(1.0, importance))
        status = DecisionStatus.ACTIVE.value if confidence >= _ACTIVE_MIN_CONF else DecisionStatus.CANDIDATE.value
        strength: float              = 1.0
        review_count: int            = 0
        last_reviewed_at: str | None = now_iso
        supersedes: str | None       = None
        
        return EventCandidateMetaClass(
            ec_id                =  ec_id,
            event_name           =  str(item.get('event_name')).strip() or 'unnamed_event',
            aliases              =  self._preprocess_listdata(item, 'aliases'),
            decision_signal      =  str(item.get('decision_signal', 'open_question')),
            summary              =  str(item.get('summary', '')).strip(),
            decision_result      =  str(item.get("decision_result", '')).strip(),
            entities             =  self._preprocess_listdata(item, 'entities'),
            evidence_message_ids =  self._preprocess_listdata(item, 'evidence_message_ids'),
            confidence           =  confidence,
            update_at            =  now_iso,
            project_id           =  project_id,
            reasons              =  self._preprocess_listdata(item, 'reasons'),
            objections           =  self._preprocess_listdata(item, 'objections'),
            alternatives         =  self._preprocess_listdata(item, 'alternatives'),
            deadline             =  str(item['deadline']).strip(),
            participants         =  self._preprocess_listdata(item, 'participants'),
            importance           =  importance,
            strength             =  strength,
            last_reviewed_at     =  last_reviewed_at,
            review_count         =  review_count,
            status               =  status,
            supersedes           =  supersedes,
        )
    
    def _preprocess_listdata(self, item: Dict, key: str) -> List[str]:
        value = item.get(key)
        if value is None: return []
        if isinstance(value, List): return [str(v) for v in value]
        return [str(value)]

    def _init_ec_save_path(self) -> None:
        with open(self._ec_save_path, mode="w", encoding="utf-8") as writer:
            writer.write("")

    def _convert_eventcandidate(self, ec: Dict[str, Any]) -> EventCandidate:
        return EventCandidate(**ec)
