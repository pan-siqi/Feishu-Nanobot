"""Sprint 1 — DecisionMemoryStore: extract + SQLite store (+ optional LightRAG)."""

from __future__ import annotations

import pytest

from nanobot.agent.hiarch_memory.decision import (
    Decision,
    DecisionExtractItem,
    DecisionExtractResult,
    DecisionMemoryStore,
)
from nanobot.providers.base import LLMResponse, LLMResponseStructure


class _FakeRag:
    def __init__(self) -> None:
        self.docs: list[str] = []

    async def ainsert(self, doc: str) -> None:
        self.docs.append(doc)


class _FakeEpisodic:
    """Minimal stand-in for EpisodicMemoryStore._rag dual-write."""

    def __init__(self) -> None:
        self._rag = _FakeRag()


class _FakeProvider:
    def __init__(self, parsed: DecisionExtractResult | None) -> None:
        self._parsed = parsed
        self._scheme = None

    def set_scheme(self, scheme: object) -> None:
        self._scheme = scheme

    async def chat_scheme(self, *args: object, **kwargs: object):
        if self._parsed is None:
            return LLMResponse(content="error", finish_reason="error")
        return LLMResponseStructure(
            content=None,
            parsed=self._parsed,
            finish_reason="stop",
            usage={},
        )


@pytest.fixture
def workspace(tmp_path):
    return tmp_path


@pytest.mark.asyncio
async def test_store_sqlite_roundtrip(workspace):
    prov = _FakeProvider(None)
    store = DecisionMemoryStore(workspace, prov, model="dummy")  # type: ignore[arg-type]
    now = 1710000000
    d = Decision(
        id="abc12345",
        project="feishu:oc_1",
        topic="auth_strategy",
        statement="Use JWT for API auth",
        reasons=["stateless", "mobile"],
        objections=["token leak concern"],
        alternatives=["session cookies"],
        decided_at=now,
        deadline=now + 86400,
        participants=["u1", "u2"],
        source="chat",
        source_ref="msg_001",
        importance=0.85,
        last_reviewed_at=now,
        review_count=0,
        strength=1.0,
        supersedes=None,
        status="active",
    )
    await store.store([d])
    got = store.get("abc12345")
    assert got is not None
    assert got.topic == "auth_strategy"
    assert got.statement == "Use JWT for API auth"
    assert got.reasons == ["stateless", "mobile"]
    assert got.objections == ["token leak concern"]
    assert got.importance == 0.85


@pytest.mark.asyncio
async def test_extract_filters_low_importance(workspace):
    parsed = DecisionExtractResult(
        result=[
            DecisionExtractItem(
                topic="trivial",
                statement="We use spaces for indent",
                importance=0.1,
            ),
            DecisionExtractItem(
                topic="deploy_window",
                statement="Production deploys only Tue/Thu",
                reasons=["change advisory board"],
                importance=0.9,
                source_ref="ref-xyz",
            ),
        ]
    )
    store = DecisionMemoryStore(workspace, _FakeProvider(parsed), model="dummy")  # type: ignore[arg-type]
    messages = [
        {"role": "user", "content": "hello", "timestamp": "2026-04-01T10:00:00"},
    ]
    out = await store.extract(messages, project="cli:direct")
    assert len(out) == 1
    assert out[0].topic == "deploy_window"
    assert out[0].project == "cli:direct"
    assert out[0].importance == 0.9


@pytest.mark.asyncio
async def test_store_dual_write_lightrag(workspace):
    episodic = _FakeEpisodic()
    prov = _FakeProvider(None)
    store = DecisionMemoryStore(workspace, prov, model="dummy", episodic=episodic)  # type: ignore[arg-type]
    now = 1710000100
    d = Decision(
        id="dec8a3f01",
        project="p1",
        topic="search_stack",
        statement="Ship Algolia first",
        reasons=["timeline"],
        objections=[],
        alternatives=["elasticsearch"],
        decided_at=now,
        deadline=None,
        participants=["alice"],
        source="cli",
        source_ref="manual",
        importance=0.8,
        last_reviewed_at=now,
        status="active",
    )
    await store.store([d])
    assert len(episodic._rag.docs) == 1
    assert "[DECISION dec8a3f01]" in episodic._rag.docs[0]
    assert "topic=search_stack" in episodic._rag.docs[0]


@pytest.mark.asyncio
async def test_extract_llm_error_returns_empty(workspace):
    store = DecisionMemoryStore(workspace, _FakeProvider(None), model="x")  # type: ignore[arg-type]
    # Force error path: provider returns LLMResponse
    async def bad_chat_scheme(*a, **k):
        return LLMResponse(content="x", finish_reason="error")

    store._provider.chat_scheme = bad_chat_scheme  # type: ignore[method-assign]
    out = await store.extract([{"role": "user", "content": "x", "timestamp": "2026-01-01"}], project="p")
    assert out == []
