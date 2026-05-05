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
        user_name     = 'nanobot',
        user_passward = '!Liwenhan123',
        url           = 'localhost',
        port          = '5432',
        database_name = 'nanobot',
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
    return SessionLocal