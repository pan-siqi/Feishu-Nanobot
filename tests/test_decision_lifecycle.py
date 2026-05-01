"""Decision memory lifecycle tests: recall/supersede/decay/review."""

from __future__ import annotations

import time

import pytest

from nanobot.agent.hiarch_memory.decision import Decision, DecisionMemoryStore


class _FakeProvider:
    def set_scheme(self, scheme):
        return None

    async def chat_scheme(self, *args, **kwargs):
        raise AssertionError("chat_scheme should not be called in lifecycle tests")


def _mk_decision(*, topic: str, statement: str, project: str = "feishu:oc_1", importance: float = 0.8) -> Decision:
    now = int(time.time())
    return Decision(
        id=f"{topic[:3]}{abs(hash(statement)) % 100000:05d}",
        project=project,
        topic=topic,
        statement=statement,
        reasons=["team consensus"],
        objections=[],
        alternatives=[],
        decided_at=now,
        deadline=None,
        participants=["alice"],
        source="chat",
        source_ref="msg-1",
        importance=importance,
        last_reviewed_at=now,
        review_count=0,
        strength=1.0,
        supersedes=None,
        status="active",
    )


@pytest.fixture
def store(tmp_path):
    return DecisionMemoryStore(tmp_path, _FakeProvider(), model="dummy")  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_store_supersede_same_topic_conflict(store: DecisionMemoryStore):
    first = _mk_decision(topic="auth_strategy", statement="Use JWT")
    second = _mk_decision(topic="auth_strategy", statement="Use signed cookies")
    await store.store([first])
    await store.store([second])

    active = store.list_by_project("feishu:oc_1")
    assert len(active) == 1
    assert active[0].statement == "Use signed cookies"
    assert active[0].supersedes == first.id

    old = store.get(first.id)
    assert old is not None
    assert old.status == "superseded"


@pytest.mark.asyncio
async def test_recall_prefers_query_match(store: DecisionMemoryStore):
    d1 = _mk_decision(topic="deploy_policy", statement="Deploy only Tue/Thu", importance=0.7)
    d2 = _mk_decision(topic="search_stack", statement="Adopt elasticsearch", importance=0.9)
    await store.store([d1, d2])

    out = store.recall("why elasticsearch", project="feishu:oc_1", limit=2)
    assert out
    assert out[0].topic == "search_stack"


@pytest.mark.asyncio
async def test_mark_review_actions(store: DecisionMemoryStore):
    d = _mk_decision(topic="incident_policy", statement="Escalate to oncall")
    await store.store([d])

    reinforced = store.mark_review(d.id, "reinforce")
    assert reinforced is not None
    assert reinforced.review_count == 1
    assert reinforced.strength > 1.0

    updated = store.mark_review(d.id, "update", new_statement="Escalate to incident commander")
    assert updated is not None
    assert updated.supersedes == d.id
    assert updated.status == "active"
    old = store.get(d.id)
    assert old is not None
    assert old.status == "superseded"

    expired = store.mark_review(updated.id, "expire")
    assert expired is not None
    assert expired.status == "expired"


@pytest.mark.asyncio
async def test_decay_and_review_candidates(store: DecisionMemoryStore):
    d = _mk_decision(topic="db_backup", statement="Backup every day", importance=0.95)
    # Make it stale enough to become a candidate
    d.last_reviewed_at = int(time.time()) - 35 * 86400
    await store.store([d])

    changed = store.decay()
    assert changed >= 1
    candidates = store.list_review_candidates(project="feishu:oc_1", limit=5)
    assert candidates
    assert candidates[0].topic == "db_backup"
