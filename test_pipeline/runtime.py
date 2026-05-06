"""E2E benchmark runtime: PostgreSQL session, provider, and project cleanup."""

from __future__ import annotations

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
from nanobot.agent.hiarch_memory.database.ec_database import EventCandidateItem, EventCandidateRepository
from nanobot.agent.hiarch_memory.decision import DecisionMemoryStore
from nanobot.providers.openai_compat_provider import OpenAICompatProvider


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def benchmark_openai_provider() -> tuple[OpenAICompatProvider, str]:
    api_key = (
        os.environ.get("NANOBOT_BENCHMARK_OPENAI_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or os.environ.get("LLM_BINDING_API_KEY")
    )
    if not api_key:
        raise RuntimeError(
            "E2E benchmark needs an API key: set OPENAI_API_KEY or NANOBOT_BENCHMARK_OPENAI_API_KEY"
        )
    api_base = (
        os.environ.get("NANOBOT_BENCHMARK_OPENAI_BASE")
        or os.environ.get("OPENAI_API_BASE")
        or os.environ.get("OPENAI_BASE_URL")
        or os.environ.get("LLM_BINDING_HOST")
        or "https://api.openai.com/v1"
    )
    model = os.environ.get("NANOBOT_BENCHMARK_MODEL", "gpt-4o-mini")
    return OpenAICompatProvider(api_key=api_key, api_base=api_base, default_model=model), model


def connect_session() -> Session:
    SessionLocal = ec_database.connect_database()
    return SessionLocal()


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


def make_benchmark_context(project: str, *, max_score: float = 0.5) -> BenchmarkContext:
    session = connect_session()
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
