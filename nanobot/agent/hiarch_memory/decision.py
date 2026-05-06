from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple
from uuid import uuid4

from loguru import logger
from sqlalchemy.orm.session import Session

from nanobot.agent.hiarch_memory.base import BaseMemoryStore
from nanobot.agent.hiarch_memory.database.ec_database import EventCandidateMetaClass, EventCandidateRepository
from nanobot.agent.hiarch_memory.scheme import DecisionStatus, EventCandidate, EventCandidateMergeResult, EventCandidateResult
from nanobot.providers.base import LLMResponse
from nanobot.providers.openai_compat_provider import OpenAICompatProvider
from nanobot.utils.helpers import format_messages
from nanobot.utils.prompt_templates import render_template


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


_ACTIVE_MIN_CONF = float(os.environ.get("NANOBOT_DECISION_ACTIVE_MIN_CONFIDENCE", "0.65"))


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
        """Canonical text blocks for top matching event candidates (system prompt)."""
        hits = self._ec_repo.retrieve(query, top_k=top_k, project=project)
        if not hits:
            return ""
        chunks = [self._ec_repo.convert_text(ec) for ec, _ in hits]
        return "## Related decisions\n\n" + "\n\n".join(chunks)

    def decay(self) -> int:
        """Apply calendar-time strength decay (see repository)."""
        return self._ec_repo.apply_decay()

    def list_review_candidates(self, project: str, limit: int = 3) -> list[EventCandidateMetaClass]:
        return self._ec_repo.list_review_candidates(project=project, limit=limit)

    async def extract(self, history: List[Dict[str, Any]], project: str | None = None) -> List[str]:
        project = project or ""
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
        result: List[Dict[str, Any]] = list(parsed.get("result") or [])
        _evidence_message_ids: List[str] = []
        for item in result:
            ev = item.get("evidence_message_ids") or []
            _evidence_message_ids.extend(ev)

        if not self._ec_repo.list(limit=1, project=project):
            for item in result:
                self._ec_repo.create(self._scheme_to_metaclass(item, project=project))
        else:
            for item in result:
                ec = self._scheme_to_metaclass(item, project=project)
                restr = self._ec_repo.retrieve(ec, project=project)
                is_create: bool = True
                if restr:
                    ec_merge = await self._merge(ec, restr, project=project)
                    if ec_merge:
                        self._ec_repo.update_by_ec_id(ec_merge)
                        is_create = False
                if is_create:
                    self._ec_repo.create(ec)
        self._ec_repo.build_embed()
        logger.info(
            "Decision extract finished: project={} candidates_in_response={} evidence_ids={}",
            project or "(none)",
            len(result),
            len(_evidence_message_ids),
        )
        return _evidence_message_ids

    async def _merge(
        self,
        ec: EventCandidateMetaClass,
        result: List[Tuple[EventCandidateMetaClass, float]],
        project: str,
    ) -> EventCandidateMetaClass | None:
        old = result[0][0]
        ec_text = self._ec_repo.convert_text(ec, remove_ec_id=True)
        ecs_text = ""
        for res in result:
            ecs_text += self._ec_repo.convert_text(res[0]).strip() + "\n\n"

        msg_eval: List[Dict[str, Any]] = [
            {
                "role": "user",
                "content": render_template(
                    "custom/evaluate.md", strip=True, event=ec_text, event_list=ecs_text
                ),
            },
        ]
        response_eval = await self._provider.chat_with_retry(
            msg_eval, model=self._model, tools=None, tool_choice=None
        )

        if not _merge_eval_bool(response_eval.content):
            return None

        msg_merge: List[Dict[str, Any]] = [
            {
                "role": "user",
                "content": render_template(
                    "custom/merge.md", strip=True, event=ec_text, event_list=ecs_text
                ),
            },
        ]
        self._provider.set_scheme(EventCandidateMergeResult)
        response_merge = await self._provider.chat_scheme(
            msg_merge, model=self._model, tools=None, tool_choice=None
        )
        if isinstance(response_merge, LLMResponse):
            raise Exception("fail to build scheme")

        parsed: Dict[str, Any] = response_merge.parsed or {}
        cand = parsed.get("event_candidate")
        if isinstance(cand, EventCandidate):
            cand = cand.model_dump()
        if not isinstance(cand, dict):
            cand = {}
        return self._scheme_to_metaclass(
            cand,
            ec_id=parsed.get("ec_id"),
            project=old.project or project,
            base=old,
        )

    def _scheme_to_metaclass(
        self,
        item: Dict[str, Any],
        ec_id: str | None = None,
        *,
        project: str = "",
        base: EventCandidateMetaClass | None = None,
    ) -> EventCandidateMetaClass:
        if not ec_id:
            ec_id = f"ec_{uuid4().hex[:10]}"
        now_iso = datetime.now(timezone.utc).isoformat()

        def _list(key: str) -> List[str]:
            v = item.get(key)
            if v is None:
                return []
            if isinstance(v, list):
                return [str(x) for x in v]
            return [str(v)]

        confidence = float(item.get("confidence", 0.0))
        importance = float(item.get("importance", confidence))
        importance = max(0.0, min(1.0, importance))

        status = (
            DecisionStatus.ACTIVE.value
            if confidence >= _ACTIVE_MIN_CONF
            else DecisionStatus.CANDIDATE.value
        )
        strength = 1.0
        review_count = 0
        last_reviewed_at: str | None = now_iso
        proj = project
        supersedes: str | None = None

        if base:
            proj = base.project or proj
            strength = float(base.strength or 1.0)
            review_count = int(base.review_count or 0)
            last_reviewed_at = base.last_reviewed_at or now_iso
            supersedes = base.supersedes
            if confidence >= _ACTIVE_MIN_CONF:
                status = DecisionStatus.ACTIVE.value
            else:
                status = base.status or status

        return EventCandidateMetaClass(
            ec_id=ec_id,
            event_name=str(item.get("event_name", "")).strip() or "unnamed_event",
            aliases=_list("aliases") if item.get("aliases") else (base.aliases if base else []),
            decision_signal=str(item.get("decision_signal", "open_question")),
            summary=str(item.get("summary", "")).strip() or "—",
            decision_result=str(item.get("decision_result", "")).strip() or "—",
            entities=_list("entities"),
            evidence_message_ids=_list("evidence_message_ids") or (base.evidence_message_ids if base else []),
            confidence=confidence,
            update_at=now_iso,
            project=proj,
            reasons=_list("reasons"),
            objections=_list("objections"),
            alternatives=_list("alternatives"),
            deadline=(str(item["deadline"]).strip() if item.get("deadline") else None),
            participants=_list("participants"),
            importance=importance,
            strength=strength,
            last_reviewed_at=last_reviewed_at,
            review_count=review_count,
            status=status,
            supersedes=supersedes,
        )

    def _init_ec_save_path(self) -> None:
        with open(self._ec_save_path, mode="w", encoding="utf-8") as writer:
            writer.write("")

    def _convert_eventcandidate(self, ec: Dict[str, Any]) -> EventCandidate:
        return EventCandidate(**ec)
