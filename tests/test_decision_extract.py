from __future__ import annotations

from dataclasses import asdict
from typing import Any

import pytest

from nanobot.agent.hiarch_memory.decision import DecisionMemoryStore, _merge_eval_bool
from nanobot.agent.hiarch_memory.scheme import EventCandidateResult
from nanobot.providers.base import LLMResponse, LLMResponseStructure


class _FakeRepo:
    def __init__(self) -> None:
        self.items: list[Any] = []

    def list(self, limit: int = 20, offset: int = 0, project: str | None = None):
        _ = limit
        _ = offset
        if project is None:
            return list(self.items)
        return [i for i in self.items if i.project == project]

    def create(self, ec):
        self.items.append(ec)
        return ec

    def retrieve(self, query, top_k: int = 5, is_filter: bool = True, project: str | None = None):
        _ = top_k
        _ = is_filter
        if hasattr(query, "event_name"):
            # for merge path in extract
            cands = self.list(project=project)
            return [(cands[0], 0.1)] if cands else []
        # for prompt block path
        return [(i, 0.1) for i in self.list(project=project)[:3]]

    def update_by_ec_id(self, ec_new, keys_selected=None):
        _ = keys_selected
        for idx, old in enumerate(self.items):
            if old.ec_id == ec_new.ec_id:
                self.items[idx] = ec_new
                return ec_new
        self.items.append(ec_new)
        return ec_new

    def build_embed(self):
        return None

    def convert_text(self, ec, remove_ec_id: bool = False):
        payload = asdict(ec)
        if remove_ec_id:
            payload.pop("ec_id", None)
        return f"event_name={payload.get('event_name')} decision_result={payload.get('decision_result')}"

    def apply_decay(self) -> int:
        return 0

    def list_review_candidates(self, *, project: str, limit: int = 3):
        _ = project
        _ = limit
        return []


class _FakeProvider:
    def __init__(self, parsed: dict[str, Any] | None, merge_decision: str = "False") -> None:
        self._parsed = parsed
        self._scheme = None
        self._merge_decision = merge_decision

    def set_scheme(self, scheme: object) -> None:
        self._scheme = scheme

    async def chat_scheme(self, *args: object, **kwargs: object):
        _ = args
        _ = kwargs
        if self._parsed is None:
            return LLMResponse(content="error", finish_reason="error")
        return LLMResponseStructure(
            content=None,
            parsed=self._parsed,
            finish_reason="stop",
            usage={},
        )

    async def chat_with_retry(self, *args: object, **kwargs: object):
        _ = args
        _ = kwargs
        return LLMResponse(content=self._merge_decision, finish_reason="stop")


@pytest.mark.asyncio
async def test_extract_create_with_project_scope(tmp_path):
    parsed = EventCandidateResult(
        result=[
            {
                "event_name": "auth_strategy",
                "decision_signal": "decided",
                "summary": "团队确认鉴权方案",
                "decision_result": "采用 JWT",
                "aliases": ["auth"],
                "entities": ["JWT"],
                "evidence_message_ids": ["m1"],
                "confidence": 0.9,
                "reasons": ["无状态架构"],
                "objections": ["token 泄露风险"],
                "alternatives": ["session"],
                "deadline": "2026-05-10",
                "participants": ["alice", "bob"],
                "importance": 0.8,
            }
        ]
    ).model_dump()
    repo = _FakeRepo()
    store = DecisionMemoryStore(
        workspace=str(tmp_path),
        mem_save_path=str(tmp_path),
        provider=_FakeProvider(parsed),
        model="dummy",
        database_session=None,  # unused in current implementation
        repo=repo,
    )
    out = await store.extract(
        [{"role": "user", "content": "我们定一下鉴权方案", "timestamp": "2026-01-01T00:00:00"}],
        project="feishu:oc_1",
    )
    assert out == ["m1"]
    assert len(repo.items) == 1
    assert repo.items[0].project == "feishu:oc_1"
    assert repo.items[0].status == "active"
    assert repo.items[0].importance == 0.8


def test_merge_eval_bool_parser():
    assert _merge_eval_bool("True")
    assert _merge_eval_bool("yes")
    assert _merge_eval_bool("是")
    assert not _merge_eval_bool("False")
    assert not _merge_eval_bool("no")


@pytest.mark.asyncio
async def test_prompt_block_for_query_respects_project(tmp_path):
    parsed = EventCandidateResult(
        result=[
            {
                "event_name": "deploy_policy",
                "decision_signal": "decided",
                "summary": "发版窗口",
                "decision_result": "周二周四发版",
                "aliases": [],
                "entities": ["prod"],
                "evidence_message_ids": ["m2"],
                "confidence": 0.9,
                "reasons": [],
                "objections": [],
                "alternatives": [],
                "deadline": None,
                "participants": [],
                "importance": 0.7,
            }
        ]
    ).model_dump()
    repo = _FakeRepo()
    store = DecisionMemoryStore(
        workspace=str(tmp_path),
        mem_save_path=str(tmp_path),
        provider=_FakeProvider(parsed),
        model="dummy",
        database_session=None,
        repo=repo,
    )
    await store.extract([{"role": "user", "content": "发版节奏", "timestamp": "2026-01-01"}], project="cli:direct")
    block_ok = store.prompt_block_for_query("发版", project="cli:direct")
    block_empty = store.prompt_block_for_query("发版", project="other:scope")
    assert "## Related decisions" in block_ok
    assert block_empty == ""
