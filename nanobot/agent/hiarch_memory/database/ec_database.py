from __future__ import annotations

import hashlib
import math
import os
from dataclasses import asdict, dataclass, fields
from datetime import datetime, timezone
from typing import Dict, List, Tuple

from numpy import ndarray
from pgvector.sqlalchemy import Vector
from sentence_transformers import SentenceTransformer
from sqlalchemy import DateTime, Float, Index, Integer, String, inspect, select, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Mapped, Session, mapped_column

from nanobot.agent.hiarch_memory.database.base import Base, connect_database
from nanobot.agent.hiarch_memory.scheme import DecisionStatus
from nanobot.utils.prompt_templates import render_template

EMBEDDING_MODEL = "bge-small-zh-v1.5"
EMBEDDING_MODEL_PATH = "./model/bge-small-zh-v1.5/"

# Forgetting / review (proposal Phase 2)
REVIEW_RETENTION_THRESHOLD = 0.4
REVIEW_IMPORTANCE_MIN = 0.6
DECAY_HALF_LIFE_DAYS = 30.0
STRENGTH_FLOOR = 0.12

# Retrieve: cosine-only ranks stale rows above fresher overrides when both stay `active`.
# After prefetching neighbors, subtract λ × normalized recency from distance (newer wins ties).
_RETRIEVE_RECENCY_LAMBDA_DEFAULT = "0.22"
_RETRIEVE_PREFETCH_MULT_DEFAULT = "5"
_RETRIEVE_PREFETCH_CAP_DEFAULT = "80"


def _parse_update_ts(update_at: str | None) -> float:
    if not update_at:
        return 0.0
    try:
        u = str(update_at).strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(u)
        return float(dt.timestamp())
    except (ValueError, TypeError, OSError):
        return 0.0


@dataclass
class EventCandidateMetaClass:
    ec_id: str
    event_name: str
    aliases: List[str]
    decision_signal: str
    summary: str
    decision_result: str
    entities: List[str]
    evidence_message_ids: List[str]
    confidence: float
    update_at: str
    project_id: str
    reasons: List[str]
    objections: List[str]
    alternatives: List[str]
    deadline: str | None
    participants: List[str]
    importance: float
    strength: float
    last_reviewed_at: str | None
    review_count: int
    status: str
    supersedes: str | None


class EventCandidateItem(Base):
    __tablename__ = "EventCandidateItem"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    ec_id: Mapped[str] = mapped_column(String)
    event_name: Mapped[str] = mapped_column(String)
    aliases: Mapped[List[str]] = mapped_column(JSONB, default=list)
    decision_signal: Mapped[str] = mapped_column(String)
    summary: Mapped[str] = mapped_column(String)
    decision_result: Mapped[str] = mapped_column(String)
    entities: Mapped[List[str]] = mapped_column(JSONB, default=list)
    evidence_message_ids: Mapped[List[str]] = mapped_column(JSONB, default=list)
    confidence: Mapped[float] = mapped_column(Float)
    update_at: Mapped[str] = mapped_column(String)

    project_id: Mapped[str] = mapped_column(String, default="")
    reasons: Mapped[List[str]] = mapped_column(JSONB, default=list)
    objections: Mapped[List[str]] = mapped_column(JSONB, default=list)
    alternatives: Mapped[List[str]] = mapped_column(JSONB, default=list)
    deadline: Mapped[str | None] = mapped_column(String, nullable=True)
    participants: Mapped[List[str]] = mapped_column(JSONB, default=list)
    importance: Mapped[float] = mapped_column(Float, default=0.5)
    strength: Mapped[float] = mapped_column(Float, default=1.0)
    last_reviewed_at: Mapped[str | None] = mapped_column(String, nullable=True)
    review_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String, default=DecisionStatus.CANDIDATE.value)
    supersedes: Mapped[str | None] = mapped_column(String, nullable=True)

    embedding: Mapped[List[float] | None] = mapped_column(Vector(512))
    embedding_model: Mapped[str | None] = mapped_column(String)
    embedding_input_hash: Mapped[str | None] = mapped_column(String)
    embedding_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index(
            "ix_items_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
            postgresql_with={"m": 16, "ef_construction": 64},
        ),
    )


def ensure_event_candidate_schema(engine: Engine) -> None:
    """Add Phase-2 columns on existing PostgreSQL deployments (idempotent)."""
    insp = inspect(engine)
    if not insp.has_table(EventCandidateItem.__tablename__):
        return
    existing = {c["name"] for c in insp.get_columns(EventCandidateItem.__tablename__)}
    table = f'"{EventCandidateItem.__tablename__}"'
    alters: list[str] = []
    if "project" not in existing:
        alters.append(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS project VARCHAR NOT NULL DEFAULT ''")
    if "reasons" not in existing:
        alters.append(
            f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS reasons JSONB NOT NULL DEFAULT '[]'::jsonb"
        )
    if "objections" not in existing:
        alters.append(
            f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS objections JSONB NOT NULL DEFAULT '[]'::jsonb"
        )
    if "alternatives" not in existing:
        alters.append(
            f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS alternatives JSONB NOT NULL DEFAULT '[]'::jsonb"
        )
    if "deadline" not in existing:
        alters.append(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS deadline VARCHAR")
    if "participants" not in existing:
        alters.append(
            f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS participants JSONB NOT NULL DEFAULT '[]'::jsonb"
        )
    if "importance" not in existing:
        alters.append(
            f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS importance DOUBLE PRECISION NOT NULL DEFAULT 0.5"
        )
    if "strength" not in existing:
        alters.append(
            f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS strength DOUBLE PRECISION NOT NULL DEFAULT 1.0"
        )
    if "last_reviewed_at" not in existing:
        alters.append(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS last_reviewed_at VARCHAR")
    if "review_count" not in existing:
        alters.append(
            f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS review_count INTEGER NOT NULL DEFAULT 0"
        )
    if "status" not in existing:
        alters.append(
            f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS status VARCHAR NOT NULL DEFAULT 'candidate'"
        )
    if "supersedes" not in existing:
        alters.append(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS supersedes VARCHAR")
    if not alters:
        return
    with engine.begin() as conn:
        for stmt in alters:
            conn.execute(text(stmt))


def compute_retention(strength: float, delta_days: float) -> float:
    return math.exp(-delta_days / max(strength, 0.01))


def _parse_iso_dt(value: str | None) -> datetime | None:
    if not value or not str(value).strip():
        return None
    try:
        s = str(value).strip().replace("Z", "+00:00")
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def item_row_to_meta(row: EventCandidateItem) -> EventCandidateMetaClass:
    keys = [f.name for f in fields(EventCandidateMetaClass)]
    return EventCandidateMetaClass(**{k: getattr(row, k) for k in keys})


class EventCandidateRepository:
    def __init__(self, session: Session, batch_size: int = 32, max_score: float = 0.5):
        self.session = session
        self._embed_model = SentenceTransformer(EMBEDDING_MODEL_PATH)
        self._batch_size: int = batch_size
        self._max_score: float = max_score

    def create(self, ec: EventCandidateMetaClass) -> EventCandidateItem:
        payload = asdict(ec)
        eventcandidate = EventCandidateItem(**payload)
        self.session.add(eventcandidate)
        self.session.commit()
        self.session.refresh(eventcandidate)
        return eventcandidate

    def get_by_id(self, id: int) -> EventCandidateItem | None:
        return self.session.get(EventCandidateItem, id)

    def get_by_ec_id(self, ec_id: str) -> EventCandidateItem | None:
        stmt = select(EventCandidateItem).where(EventCandidateItem.ec_id == ec_id)
        return self.session.scalar(stmt)

    def update_by_ec_id(self, ec_new: EventCandidateMetaClass, keys_selected: List | None = None):
        ec = self.get_by_ec_id(ec_new.ec_id)
        if ec is None:
            return None

        if keys_selected is None:
            ec_new_dict: Dict = asdict(ec_new)
            for key, value in ec_new_dict.items():
                setattr(ec, key, value)
            ec.embedding = None
            ec.embedding_model = None
            ec.embedding_input_hash = None
            ec.embedding_updated_at = None
        else:
            for key in keys_selected:
                ec_new_value = getattr(ec_new, key)
                setattr(ec, key, ec_new_value)

        self.session.commit()
        self.session.refresh(ec)
        return ec

    def list(self, project_id: str, limit: int=20, offset: int=0) -> list[EventCandidateItem]:
        stmt = (
            select(EventCandidateItem)
            .where(EventCandidateItem.project_id == project_id)
            .order_by(EventCandidateItem.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(self.session.scalars(stmt))

    def build_embed(self) -> None:
        stmt = (
            select(EventCandidateItem)
            .where(EventCandidateItem.embedding.is_(None))
            .limit(self._batch_size)
        )
        ecs = self.session.scalars(stmt).all()
        texts: List[str] = []
        texts_hash: List[str] = []

        for ec in ecs:
            t = self.convert_text(ec)
            txthash = self._stable_hash(t)
            texts.append(t)
            texts_hash.append(txthash)

        embeddings: ndarray = self._embed_model.encode(texts, batch_size=self._batch_size, normalize_embeddings=True)
        for idx, ec in enumerate(ecs):
            ec.embedding = embeddings[idx, :]
            ec.embedding_model = EMBEDDING_MODEL
            ec.embedding_input_hash = texts_hash[idx]
            ec.embedding_updated_at = _now_utc()

        self.session.commit()

    def retrieve(
        self,
        query: EventCandidateMetaClass | str,
        project_id: str,
        top_k: int = 5,
        is_filter: bool = True,
    ) -> List[Tuple[EventCandidateMetaClass, float]]:
        query_string: str = self.convert_text(query) if isinstance(query, EventCandidateMetaClass) else str(query)
        query_vector = self._embed_model.encode([query_string], normalize_embeddings=True).flatten()
        distance = EventCandidateItem.embedding.cosine_distance(query_vector).label("distance")
        excluded_status = (DecisionStatus.SUPERSEDED.value, DecisionStatus.EXPIRED.value, DecisionStatus.ARCHIVED.value)
        stmt = (
            select(EventCandidateItem, distance)
            .where(EventCandidateItem.embedding.is_not(None))
            .where(EventCandidateItem.status.notin_(excluded_status))
            .where(EventCandidateItem.project_id == project_id)
            .order_by(distance)
            .limit(top_k)
        )

        result: List[Tuple[EventCandidateItem, float]] = self.session.execute(stmt).all()
        if is_filter: result = list(filter(lambda item: item[1] < self._max_score, result))

        out: List[Tuple[EventCandidateMetaClass, float]] = []
        keys = [f.name for f in fields(EventCandidateMetaClass)]
        for item in result:
            _dict = {key: getattr(item[0], key) for key in keys}
            out.append((EventCandidateMetaClass(**_dict), item[1]))
        return out

    def convert_text(self, ec: EventCandidateMetaClass | EventCandidateItem, remove_ec_id: bool = False) -> str:
        _keys = [f.name for f in fields(EventCandidateMetaClass)]
        if remove_ec_id:
            _keys.remove("ec_id")
        _dict = {key: getattr(ec, key) for key in _keys}
        return render_template("custom/canonical.md", strip=True, **_dict)

    def _stable_hash(self, text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def apply_decay(self) -> int:
        stmt = select(EventCandidateItem).where(
            EventCandidateItem.status.in_(
                [DecisionStatus.ACTIVE.value, DecisionStatus.CANDIDATE.value]
            )
        )
        rows = list(self.session.scalars(stmt))
        now = _now_utc()
        changed = 0
        for row in rows:
            ref = _parse_iso_dt(row.last_reviewed_at) or _parse_iso_dt(row.update_at) or now
            if ref.tzinfo is None:
                ref = ref.replace(tzinfo=timezone.utc)
            delta_days = max(0.0, (now - ref).total_seconds() / 86400.0)
            factor = math.exp(-delta_days / DECAY_HALF_LIFE_DAYS)
            old = float(row.strength or 1.0)
            new_s = max(STRENGTH_FLOOR, old * factor)
            if abs(new_s - old) > 1e-6:
                row.strength = new_s
                changed += 1
        if changed:
            self.session.commit()
        return changed

    def list_review_candidates(
        self,
        *,
        project: str,
        limit: int = 3,
        retention_threshold: float = REVIEW_RETENTION_THRESHOLD,
        importance_min: float = REVIEW_IMPORTANCE_MIN,
    ) -> list[EventCandidateMetaClass]:
        stmt = (
            select(EventCandidateItem)
            .where(EventCandidateItem.project == project)
            .where(EventCandidateItem.status == DecisionStatus.ACTIVE.value)
            .where(EventCandidateItem.importance > importance_min)
        )
        rows = list(self.session.scalars(stmt))
        now = _now_utc()
        scored: list[tuple[float, EventCandidateItem]] = []
        for row in rows:
            ref = _parse_iso_dt(row.last_reviewed_at) or _parse_iso_dt(row.update_at) or now
            if ref.tzinfo is None:
                ref = ref.replace(tzinfo=timezone.utc)
            delta_days = max(0.0, (now - ref).total_seconds() / 86400.0)
            r = compute_retention(float(row.strength or 1.0), delta_days)
            if r < retention_threshold:
                scored.append((r, row))
        scored.sort(key=lambda x: x[0])
        return [item_row_to_meta(r) for _, r in scored[:limit]]


__all__ = [
    "EventCandidateItem",
    "EventCandidateMetaClass",
    "EventCandidateRepository",
    "compute_retention",
    "connect_database",
    "ensure_event_candidate_schema",
    "item_row_to_meta",
]
