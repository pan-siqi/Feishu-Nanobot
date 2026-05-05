from nanobot.agent.hiarch_memory.database.base import Base, connect_database
from nanobot.utils.prompt_templates import render_template
from sqlalchemy import create_engine, select, String, DateTime, Index, Float
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker, Session
from sqlalchemy import text
from pgvector.sqlalchemy import Vector
from datetime import datetime, timezone
from typing import List, Dict, Tuple
from dataclasses import dataclass, asdict, fields
from numpy import ndarray
from sentence_transformers import SentenceTransformer
import hashlib

EMBEDDING_MODEL = 'bge-small-zh-v1.5'
EMBEDDING_MODEL_PATH = './model/bge-small-zh-v1.5/'

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

class EventCandidateItem(Base):
    # table name
    __tablename__ = 'EventCandidateItem'
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    
    # item name    
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
    
    # embedding item
    embedding: Mapped[List[float] | None] = mapped_column(Vector(512))
    embedding_model: Mapped[str | None] = mapped_column(String)
    embedding_input_hash: Mapped[str | None] = mapped_column(String)
    embedding_updated_at: Mapped[datetime | None] = mapped_column(DateTime)

    # table args
    __table_args__ = (
        Index(
            "ix_items_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
            postgresql_with={"m": 16, "ef_construction": 64},
        ),
    )


class EventCandidateRepository:
    def __init__(self, session: Session, batch_size: int=32, max_score: float=0.5):
        self.session = session
        self._embed_model = SentenceTransformer(EMBEDDING_MODEL_PATH)
        self._batch_size: int = batch_size
        self._max_score: float = max_score
    
    def create(self, ec: EventCandidateMetaClass) -> EventCandidateItem:
        eventcandidate = EventCandidateItem(**asdict(ec))
        self.session.add(eventcandidate)
        self.session.commit()
        self.session.refresh(eventcandidate)
        return eventcandidate

    def get_by_id(self, id: int) -> EventCandidateItem | None:
        return self.session.get(EventCandidateItem, id)
    
    def get_by_ec_id(self, ec_id: str) -> EventCandidateItem | None:
        stmt = select(EventCandidateItem).where(EventCandidateItem.ec_id == ec_id)
        return self.session.scalar(stmt)
    
    def update_by_ec_id(self, ec_new: EventCandidateMetaClass, keys_selected: List | None=None):
        ec = self.get_by_ec_id(ec_new.ec_id)
        if ec is None: return None

        # update some key
        if keys_selected is None:
            ec_new_dict: Dict = asdict(ec_new)
            for key, value in ec_new_dict.items(): # update all key value
                setattr(ec, key, value)
        else:
            for key in keys_selected:
                ec_new_value = getattr(ec_new, key)
                setattr(ec, key, ec_new_value)

        self.session.commit()
        self.session.refresh(ec)
        return ec

    def list(self, limit: int = 20, offset: int = 0) -> list[EventCandidateItem]:
        stmt = (
            select(EventCandidateItem)
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
            text = self._convert_text(ec)
            txthash = self._stable_hash(text)
            texts.append(text)
            texts_hash.append(txthash)
        
        # convert to vector parallel
        embeddings: ndarray = self._embed_model.encode(texts, batch_size=self._batch_size, normalize_embeddings=True)

        for idx, ec in enumerate(ecs):
            ec.embedding = embeddings[idx, :]
            ec.embedding_model = EMBEDDING_MODEL
            ec.embedding_input_hash = texts_hash[idx]
            ec.embedding_updated_at = datetime.now().isoformat()

        self.session.commit()
    
    def retrieve(self, ec: EventCandidateMetaClass, top_k: int = 5, is_filter: bool = True) -> List[Tuple[EventCandidateMetaClass, float]]:
        '''
        retures: [(ec1, score1), (ec1, score2), (ec1, score3), ...]
        score_i, small means good
        '''
        text = self._convert_text(ec)
        query_vector = self._embed_model.encode([text], normalize_embeddings=True).flatten()
        distance = EventCandidateItem.embedding.cosine_distance(query_vector).label("distance")
        stmt = (
            select(EventCandidateItem, distance)
            .where(EventCandidateItem.embedding.is_not(None))
            .order_by(distance)
            .limit(top_k)
        )
        result: List[Tuple[EventCandidateItem, float]] = self.session.execute(stmt).all()
        if is_filter: result = list(filter(lambda item: item[1] < self._max_score, result))

        _result: List[Tuple] = list()
        _keys = [f.name for f in fields(ec)]
        for item in result: # item --> metaclass
            _dict = {key: getattr(item[0], key) for key in _keys}
            ec_item = EventCandidateMetaClass(**_dict)
            _result.append((ec_item, item[1]))
        return _result
    
    def convert_text(self, ec: EventCandidateMetaClass, remove_ec_id: bool = False) -> str: # `EventCandidateMetaClass` --> `str`
        _keys = [f.name for f in fields(ec) if remove_ec_id and f.name != 'ec_id']
        _dict = dict()
        for key in _keys: _dict[key] = getattr(ec, key)
        return render_template('custom/canonical.md', strip=True, **_dict)

    def _stable_hash(self, text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()