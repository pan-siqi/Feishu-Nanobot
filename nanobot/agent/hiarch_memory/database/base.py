import os

from sqlalchemy import create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy.orm.session import Session
from dataclasses import dataclass

@dataclass
class PostgresqlConfig:
    user_name: str
    user_passward: str
    url: str
    port: str
    database_name: str

    def get_string(self) -> str:
        return "postgresql+psycopg://{user_name}:{user_passward}@{url}:{port}/{database_name}"\
        .format(
            user_name = self.user_name,
            user_passward = self.user_passward,
            url=self.url,
            port=self.port,
            database_name=self.database_name,
        )

class Base(DeclarativeBase):
    pass

def connect_database() -> Session:
    postgresql_config = PostgresqlConfig(
        user_name=os.environ.get("NANOBOT_PG_USER", "nanobot"),
        user_passward=os.environ.get("NANOBOT_PG_PASSWORD", ""),
        url=os.environ.get("NANOBOT_PG_HOST", "localhost"),
        port=os.environ.get("NANOBOT_PG_PORT", "5432"),
        database_name=os.environ.get("NANOBOT_PG_DATABASE", "nanobot"),
    )
    engine = create_engine(
        postgresql_config.get_string(),
        echo=False,
    )

    SessionLocal: Session = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
    )

    Base.metadata.create_all(engine)

    # Phase 2: add columns on existing DBs (no-op if already present)
    from nanobot.agent.hiarch_memory.database.ec_database import ensure_event_candidate_schema

    ensure_event_candidate_schema(engine)
    return SessionLocal