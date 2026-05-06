"""Decision memory lifecycle tests for current EventCandidate store."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta, timezone

import pytest

from nanobot.agent.hiarch_memory.decision import DecisionMemoryStore


class _FakeRepo:
    def __init__(self) -> None:
        self.items = []

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
            cands = self.list(project=project)
            return [(cands[0], 0.1)] if cands else []
        return [(i, 0.1) for i in self.list(project=project)]

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
        data = asdict(ec)
        if remove_ec_id:
            data.pop("ec_id", None)
        return f"event={data.get('event_name')} result={data.get('decision_result')}"

    def apply_decay(self) -> int:
        changed = 0
        now = datetime.now(timezone.utc)
        for item in self.items:
            ref = datetime.fromisoformat(item.last_reviewed_at)
            delta_days = max(0.0, (now - ref).total_seconds() / 86400.0)
            if delta_days > 30 and item.status == "active":
                item.strength = max(0.12, item.strength * 0.5)
                changed += 1
        return changed

    def list_review_candidates(self, *, project: str, limit: int = 3):
        rows = [i for i in self.items if i.project == project and i.status == "active" and i.importance > 0.6]
        rows.sort(key=lambda x: x.strength)
        return rows[:limit]

    def get_by_ec_id(self, ec_id: str):
        for i in self.items:
            if i.ec_id == ec_id:
                return i
        return None


class _FakeProvider:
    def __init__(self, parsed=None, merge_decision: str = "False") -> None:
        self._parsed = parsed
        self._merge_decision = merge_decision

    def set_scheme(self, scheme):
        _ = scheme
        return None

    async def chat_scheme(self, *args, **kwargs):
        _ = args
        _ = kwargs
        from nanobot.providers.base import LLMResponseStructure

        return LLMResponseStructure(content=None, parsed=self._parsed, finish_reason="stop", usage={})

    async def chat_with_retry(self, *args, **kwargs):
        _ = args
        _ = kwargs
        from nanobot.providers.base import LLMResponse

        return LLMResponse(content=self._merge_decision, finish_reason="stop")


@pytest.fixture
def store(tmp_path):
    repo = _FakeRepo()
    provider = _FakeProvider(
        parsed={
            "result": [
                {
                    "event_name": "db_backup",
                    "decision_signal": "decided",
                    "summary": "备份策略确定",
                    "decision_result": "每日备份",
                    "aliases": ["backup"],
                    "entities": ["db"],
                    "evidence_message_ids": ["m10"],
                    "confidence": 0.9,
                    "reasons": ["合规要求"],
                    "objections": [],
                    "alternatives": ["每周备份"],
                    "deadline": None,
                    "participants": ["alice"],
                    "importance": 0.95,
                }
            ]
        }
    )
    return DecisionMemoryStore(
        workspace=str(tmp_path),
        mem_save_path=str(tmp_path),
        provider=provider,
        model="dummy",
        database_session=None,
        repo=repo,
    )


@pytest.mark.asyncio
async def test_extract_sets_active_status_and_project(store: DecisionMemoryStore):
    await store.extract([{"role": "user", "content": "确定备份策略", "timestamp": "2026-01-01"}], project="feishu:oc_1")
    assert store.has_any_candidates(project="feishu:oc_1")
    assert not store.has_any_candidates(project="feishu:other")
    block = store.prompt_block_for_query("备份", project="feishu:oc_1")
    assert "## Related decisions" in block
    block_other = store.prompt_block_for_query("备份", project="feishu:other")
    assert block_other == ""


def test_decay_and_review_candidates_delegate(store: DecisionMemoryStore):
    old = store._scheme_to_metaclass(  # noqa: SLF001
        {
            "event_name": "db_backup",
            "decision_signal": "decided",
            "summary": "备份策略确定",
            "decision_result": "每日备份",
            "aliases": ["backup"],
            "entities": ["db"],
            "evidence_message_ids": ["m10"],
            "confidence": 0.9,
            "reasons": ["合规要求"],
            "objections": [],
            "alternatives": ["每周备份"],
            "deadline": None,
            "participants": ["alice"],
            "importance": 0.95,
        },
        project="feishu:oc_1",
    )
    old.last_reviewed_at = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
    store._ec_repo.create(old)  # noqa: SLF001
    changed = store.decay()
    assert changed >= 1
    cands = store.list_review_candidates(project="feishu:oc_1", limit=5)
    assert cands
    assert cands[0].event_name == "db_backup"
