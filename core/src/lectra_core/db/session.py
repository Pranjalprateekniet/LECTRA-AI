"""Database session and engine management."""

from collections.abc import Generator
from typing import Dict, Optional

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from lectra_core.config import Settings, get_settings
from lectra_core.db.base import Base

_ENGINES: Dict[str, Engine] = {}
_SESSION_FACTORIES: Dict[str, sessionmaker[Session]] = {}


def _enable_sqlite_pragmas(dbapi_con, con_record) -> None:
    """Enforce foreign key constraints and WAL journal mode on SQLite connections."""
    cursor = dbapi_con.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


def get_engine(settings: Optional[Settings] = None) -> Engine:
    """Create or return cached SQLAlchemy engine for the configured database URL."""
    if settings is None:
        settings = get_settings()

    db_url = settings.database_url
    if db_url in _ENGINES:
        return _ENGINES[db_url]

    settings.ensure_directories()
    connect_args = {}
    if db_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False

    engine = create_engine(
        db_url,
        connect_args=connect_args,
        echo=settings.debug,
    )

    if db_url.startswith("sqlite"):
        event.listen(engine, "connect", _enable_sqlite_pragmas)

    _ENGINES[db_url] = engine
    return engine


def get_session_factory(settings: Optional[Settings] = None) -> sessionmaker[Session]:
    """Create or return cached sessionmaker for the configured database URL."""
    if settings is None:
        settings = get_settings()

    db_url = settings.database_url
    if db_url in _SESSION_FACTORIES:
        return _SESSION_FACTORIES[db_url]

    engine = get_engine(settings)
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    _SESSION_FACTORIES[db_url] = factory
    return factory


def get_db(settings: Optional[Settings] = None) -> Generator[Session, None, None]:
    """Dependency / context generator yielding a database session."""
    factory = get_session_factory(settings)
    session = factory()
    try:
        yield session
    finally:
        session.close()


def init_db(engine: Optional[Engine] = None, settings: Optional[Settings] = None) -> None:
    """Initialize database tables using Base metadata."""
    if engine is None:
        engine = get_engine(settings)
    Base.metadata.create_all(bind=engine)
