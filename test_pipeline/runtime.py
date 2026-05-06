"""E2E benchmark runtime: PostgreSQL session, provider, and project cleanup."""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import delete
from sqlalchemy.orm import Session

from nanobot.agent.hiarch_memory.database import ec_database
from nanobot.agent.hiarch_memory.database.base import Base
from nanobot.agent.hiarch_memory.database.ec_database import (
    EventCandidateItem,
    EventCandidateRepository,
    ensure_event_candidate_schema,
)
import shutil

from nanobot.agent.hiarch_memory.decision import DecisionMemoryStore
from nanobot.agent.hiarch_memory.episodic import EpisodicMemoryStore
from nanobot.agent.hiarch_memory.memory import HiarchMemoryStore
from nanobot.agent.hiarch_memory.router import Router
from nanobot.providers.openai_compat_provider import OpenAICompatProvider


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _llm_from_nanobot_config() -> tuple[str | None, str | None, str | None]:
    """当环境变量未设置时，从 `.nanobot/config.json` 的 `providers.custom` 读取（与 fsbot 同源）。"""
    path = _repo_root() / ".nanobot" / "config.json"
    if not path.is_file():
        return None, None, None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None, None, None
    prov = (data.get("providers") or {}).get("custom") or {}
    key = (prov.get("apiKey") or prov.get("api_key") or "").strip() or None
    base = (prov.get("apiBase") or prov.get("api_base") or "").strip() or None
    ag = (data.get("agents") or {}).get("defaults") or {}
    model = (ag.get("model") or "").strip() or None
    return key, base, model


def benchmark_openai_provider() -> tuple[OpenAICompatProvider, str]:
    file_key, file_base, file_model = _llm_from_nanobot_config()
    api_key = (
        os.environ.get("NANOBOT_BENCHMARK_OPENAI_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or os.environ.get("LLM_BINDING_API_KEY")
        or file_key
    )
    if not api_key:
        raise RuntimeError(
            "E2E benchmark needs an API key: set OPENAI_API_KEY / NANOBOT_BENCHMARK_OPENAI_API_KEY / "
            "LLM_BINDING_API_KEY, or configure providers.custom in .nanobot/config.json"
        )
    api_base = (
        os.environ.get("NANOBOT_BENCHMARK_OPENAI_BASE")
        or os.environ.get("OPENAI_API_BASE")
        or os.environ.get("OPENAI_BASE_URL")
        or os.environ.get("LLM_BINDING_HOST")
        or file_base
        or "https://api.openai.com/v1"
    )
    model = os.environ.get("NANOBOT_BENCHMARK_MODEL") or file_model or "gpt-4o-mini"
    return OpenAICompatProvider(api_key=api_key, api_base=api_base, default_model=model), model


def connect_session() -> Session:
    SessionLocal = ec_database.connect_database()
    return SessionLocal()


def init_decision_schema(session: Session) -> None:
    """Create EventCandidateItem table + Phase-2 columns (pgvector + JSONB)."""
    engine = session.get_bind()
    Base.metadata.create_all(engine)
    ensure_event_candidate_schema(engine)


def delete_project_rows(session: Session, project: str) -> None:
    session.execute(delete(EventCandidateItem).where(EventCandidateItem.project == project))
    session.commit()


@dataclass
class BenchmarkContext:
    workspace: str
    mem_save_path: str
    session: Session
    repo: EventCandidateRepository
    store: DecisionMemoryStore
    model: str
    cleanup_project: Callable[[], None]

    def close(self) -> None:
        self.session.close()


@dataclass
class RouterPipelineContext:
    """Router + Episodic + Decision + Hiarch（同一 workspace，供整条链路压测）。"""

    workspace: str
    mem_save_path: str
    history_save_path: str
    session: Session
    repo: EventCandidateRepository
    decision: DecisionMemoryStore
    episodic: EpisodicMemoryStore
    router: Router
    hiarch: HiarchMemoryStore
    model: str
    project: str

    def close(self) -> None:
        delete_project_rows(self.session, self.project)
        self.session.close()
        shutil.rmtree(self.workspace, ignore_errors=True)


def make_router_pipeline_context(project: str, *, max_score: float = 0.5) -> RouterPipelineContext:
    session = connect_session()
    init_decision_schema(session)
    delete_project_rows(session, project)

    root = _repo_root()
    wd = tempfile.mkdtemp(prefix="nanobot-router-", dir=str(root / ".nanobot"))
    workspace = wd
    mem_save_path = str(Path(workspace) / "memory")
    Path(mem_save_path).mkdir(parents=True, exist_ok=True)
    history_save_path = str(Path(mem_save_path) / ".history.jsonl")

    provider, model = benchmark_openai_provider()
    repo = EventCandidateRepository(session, batch_size=32, max_score=max_score)
    decision = DecisionMemoryStore(
        workspace=workspace,
        mem_save_path=mem_save_path,
        provider=provider,
        model=model,
        database_session=session,
        repo=repo,
    )
    episodic = EpisodicMemoryStore(workspace, mem_save_path, provider, model)
    router = Router(mem_save_path, history_save_path, episodic, decision)
    hiarch = HiarchMemoryStore(workspace, episodic, decision)

    return RouterPipelineContext(
        workspace=workspace,
        mem_save_path=mem_save_path,
        history_save_path=history_save_path,
        session=session,
        repo=repo,
        decision=decision,
        episodic=episodic,
        router=router,
        hiarch=hiarch,
        model=model,
        project=project,
    )


def make_benchmark_context(project: str, *, max_score: float = 0.5) -> BenchmarkContext:
    session = connect_session()
    init_decision_schema(session)
    session.execute(delete(EventCandidateItem).where(EventCandidateItem.project == project))
    session.commit()

    root = _repo_root()
    wd = tempfile.mkdtemp(prefix="nanobot-bench-", dir=str(root / ".nanobot"))
    mem_save_path = str(Path(wd) / "memory")
    Path(mem_save_path).mkdir(parents=True, exist_ok=True)

    provider, model = benchmark_openai_provider()
    repo = EventCandidateRepository(session, batch_size=32, max_score=max_score)
    store = DecisionMemoryStore(
        workspace=wd,
        mem_save_path=mem_save_path,
        provider=provider,
        model=model,
        database_session=session,
        repo=repo,
    )

    def cleanup_project() -> None:
        delete_project_rows(session, project)

    return BenchmarkContext(
        workspace=wd,
        mem_save_path=mem_save_path,
        session=session,
        repo=repo,
        store=store,
        model=model,
        cleanup_project=cleanup_project,
    )


def history_from_texts(
    texts: list[str],
    *,
    role: str = "user",
    id_prefix: str = "m",
    start: datetime | None = None,
    minutes_step: int = 1,
) -> list[dict[str, Any]]:
    """Build history dicts for DecisionMemoryStore.extract / format_messages."""
    if start is None:
        start = datetime(2026, 5, 1, 8, 0, tzinfo=timezone.utc)
    out: list[dict[str, Any]] = []
    for i, content in enumerate(texts):
        ts = start + timedelta(minutes=minutes_step * i)
        out.append(
            {
                "role": role,
                "content": content,
                "timestamp": ts.isoformat(),
                "message_id": f"{id_prefix}_{i:04d}_{uuid.uuid4().hex[:6]}",
            }
        )
    return out


def decision_hit(decision_result: str, substrings: list[str]) -> bool:
    low = decision_result.lower()
    for s in substrings:
        if s.lower() in low or s in decision_result:
            return True
    return False


def sliding_text_windows(texts: list[str], size: int = 100, overlap: int = 20) -> list[list[str]]:
    """与 Router 相近的滑动窗口（覆盖全部消息，右端为 min(left+size, n)）。"""
    n = len(texts)
    if n == 0:
        return []
    windows: list[list[str]] = []
    left = 0
    while left < n:
        right = min(left + size, n)
        windows.append(texts[left:right])
        if right >= n:
            break
        left = right - overlap
    return windows


async def batched_decision_extract(
    store: DecisionMemoryStore,
    texts: list[str],
    project: str,
    *,
    window_size: int = 100,
    overlap: int = 20,
    id_prefix: str = "bench",
    start: datetime | None = None,
    minutes_step: int = 1,
) -> None:
    """按窗口多次调用 extract，贴近 Router 卸批（不跑 Episodic）。"""
    for wi, chunk in enumerate(sliding_text_windows(texts, size=window_size, overlap=overlap)):
        hist = history_from_texts(
            chunk,
            id_prefix=f"{id_prefix}_w{wi}",
            start=start,
            minutes_step=minutes_step,
        )
        await store.extract(hist, project=project)
