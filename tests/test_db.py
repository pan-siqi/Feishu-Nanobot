from sqlalchemy import create_engine, select, String, DateTime, Index
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy.orm.session import Session
from sqlalchemy import text
from pgvector.sqlalchemy import Vector
from datetime import datetime, timezone
import hashlib
import numpy as np
from numpy import ndarray
from typing import List, Dict
from sentence_transformers import SentenceTransformer

EMBEDDING_MODEL = 'bge-small-zh-v1.5'
EMBEDDING_MODEL_PATH = './model/bge-small-zh-v1.5/'

class Base(DeclarativeBase):
    pass

class Item(Base):
    __tablename__ = "items"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str | None] = mapped_column(String)
    category: Mapped[str | None] = mapped_column(String)
    description: Mapped[str | None] = mapped_column(String)

    embedding: Mapped[list[float] | None] = mapped_column(Vector(512))
    embedding_model: Mapped[str | None] = mapped_column(String)
    embedding_input_hash: Mapped[str | None] = mapped_column(String)
    embedding_updated_at: Mapped[datetime | None] = mapped_column(DateTime)

    __table_args__ = (
        Index(
            "ix_items_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
            postgresql_with={"m": 16, "ef_construction": 64},
        ),
    )

engine = create_engine(
    # "sqlite:///{}".format("./tests/workspace/memory/test.db"),
    "postgresql+psycopg://nanobot:!Liwenhan123@localhost:5432/nanobot",
    echo=False,
)

# with engine.begin() as conn:
#     conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
#     Base.metadata.create_all(conn)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)

Base.metadata.create_all(engine)

class ItemRepository:
    def __init__(self, session: Session):
        self.session = session
        self._embed_model = SentenceTransformer(EMBEDDING_MODEL_PATH)
        self._batch_size: int = 32

    def create(self, name: str, category: str, description: str) -> Item:
        item = Item(name=name, category=category, description=description)
        self.session.add(item)
        self.session.commit()
        self.session.refresh(item)
        return item

    def get_by_id(self, id: int) -> Item | None:
        return self.session.get(Item, id)

    def get_by_email(self, email: str) -> Item | None:
        stmt = select(Item).where(Item.email == email)
        return self.session.scalar(stmt)

    def list(self, limit: int = 20, offset: int = 0) -> list[Item]:
        stmt = (
            select(Item)
            .order_by(Item.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(self.session.scalars(stmt))

    def update_age(self, item_id: int, age: int) -> Item | None:
        item = self.get_by_id(item_id)

        if item is None:
            return None

        item.age = age
        self.session.commit()
        self.session.refresh(item)
        return item

    def delete(self, item_id: int) -> bool:
        item = self.get_by_id(item_id)

        if item is None:
            return False

        self.session.delete(item)
        self.session.commit()
        return True

    def build_embedding(self) -> str:
        stmt = (
            select(Item)
            .where(Item.embedding.is_(None))
            .limit(self._batch_size)
        )
        items = self.session.scalars(stmt).all()
        texts: List[str] = []
        texts_hash: List[str] = []
        
        for item in items:
            text = self.convert_text(item)
            txthash = self.stable_hash(text)
            texts.append(text)
            texts_hash.append(txthash)
        
        # convert to vector parallel
        embeddings: ndarray = self._embed_model.encode(texts, batch_size=self._batch_size, normalize_embeddings=True)

        for idx, item in enumerate(items):
            item.embedding = embeddings[idx, :]
            item.embedding_model = EMBEDDING_MODEL
            item.embedding_input_hash = texts_hash[idx]
            item.embedding_updated_at = datetime.now(timezone.utc)

        self.session.commit()

    def search_similar_items(self, item: Item, top_k: int = 5):
        text = self.convert_text(item)
        query_vector = self._embed_model.encode([text], normalize_embeddings=True).flatten()
        distance = Item.embedding.cosine_distance(query_vector).label("distance")
        stmt = (
            select(Item, distance)
            .where(Item.embedding.is_not(None))
            .order_by(distance)
            .limit(top_k)
        )
        return self.session.execute(stmt).all()
    
    def convert_text(self, item: Item):
        return 'name: {}\ncategory: {}\ndescription: {}'.format(item.name, item.category, item.description)

    def stable_hash(self, text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

if __name__ == '__main__':
    with SessionLocal() as session:
        repo = ItemRepository(session)

        # item1 = repo.create("Bot", "animal", "It's a people")
        # item2 = repo.create("Tomato", "planet", "It's a kind of planet")

        repo.build_embedding()
        print(repo.list())

        # repo.delete(3)
        # repo.delete(4)

        # print(repo.list())