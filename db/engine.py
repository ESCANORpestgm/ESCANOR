"""SQLAlchemy engine and session plumbing for ESCANOR's relational store.

The default target is a file-backed SQLite database under ``results/``, so the
platform keeps running with no infrastructure to provision. Setting
``DATABASE_URL`` to a PostgreSQL DSN moves the exact same code onto a server —
nothing in :mod:`db.models` or :mod:`db.repository` is SQLite-specific except
the pragmas below.

The engine is a lazily-built process singleton: creating one per call would
defeat the connection pool, which is the main reason this module exists — the
predecessor ``sqlite3.connect`` helper opened a fresh connection per query and
never closed it.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from threading import Lock

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from data import paths

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None
_build_lock = Lock()


def _build_engine(url: str) -> Engine:
    kwargs: dict = {"pool_pre_ping": True, "future": True}

    if url.startswith("sqlite"):
        # The API process and the APScheduler retrain/refresh jobs share the
        # file from more than one thread, and SQLite's default
        # ``check_same_thread`` would reject that outright.
        kwargs["connect_args"] = {"check_same_thread": False, "timeout": 20.0}
        return _build_sqlite_engine(url, kwargs)

    return create_engine(url, pool_size=5, max_overflow=10, **kwargs)


def _build_sqlite_engine(url: str, kwargs: dict) -> Engine:
    """Build a SQLite engine and attach the pragma listener to that engine."""
    engine = create_engine(url, **kwargs)

    @event.listens_for(engine, "connect")
    def _apply_sqlite_pragmas(dbapi_connection, _connection_record):
        # WAL is the important one: with the default rollback journal a writer
        # blocks every reader, so a retrain-log insert landing during a dashboard
        # poll would surface "database is locked". WAL lets the readers run
        # concurrently with the single writer.
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def get_engine() -> Engine:
    """Return the process-wide engine, building it on first use."""
    global _engine, _session_factory
    with _build_lock:
        if _engine is None:
            url = paths.database_url()
            paths.RESULTS_ROOT.mkdir(parents=True, exist_ok=True)
            _engine = _build_engine(url)
            # ``expire_on_commit=False`` keeps loaded rows readable after the
            # session closes, so repository functions can return ORM objects
            # without leaving detached-attribute traps for the caller.
            _session_factory = sessionmaker(bind=_engine, expire_on_commit=False, future=True)
    return _engine


def dispose_engine() -> None:
    """Tear the singleton down — required when a test repoints ``DATABASE_URL``."""
    global _engine, _session_factory
    with _build_lock:
        if _engine is not None:
            _engine.dispose()
        _engine = None
        _session_factory = None


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional scope: commit on success, roll back on error, always close.

    This replaces the ``with sqlite3.connect(...) as connection`` pattern, whose
    context manager commits but never closes the connection.
    """
    get_engine()
    if _session_factory is None:  # pragma: no cover - get_engine() guarantees it
        raise RuntimeError("SQLAlchemy session factory was not initialised")
    session = _session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
