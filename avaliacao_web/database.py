from __future__ import annotations

from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import DATABASE_PATH, DATABASE_URL


class Base(DeclarativeBase):
    pass


sqlite_connect_args = (
    {"check_same_thread": False}
    if DATABASE_URL.startswith("sqlite")
    else {}
)

engine = create_engine(
    DATABASE_URL,
    connect_args=sqlite_connect_args,
    future=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    class_=Session,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


if DATABASE_URL.startswith("sqlite"):

    @event.listens_for(Engine, "connect")
    def configure_sqlite(
        dbapi_connection,
        connection_record,
    ) -> None:
        del connection_record
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()


def initialize_database() -> None:
    # Import local para registrar todos os modelos no metadata.
    from . import models  # noqa: F401

    Base.metadata.create_all(bind=engine)


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    session = SessionLocal()

    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def database_status() -> dict[str, object]:
    initialize_database()

    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))

    table_names = sorted(inspect(engine).get_table_names())

    return {
        "connected": True,
        "backend": engine.url.get_backend_name(),
        "database_path": str(DATABASE_PATH),
        "tables": table_names,
        "table_count": len(table_names),
    }
