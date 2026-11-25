"""
Database engine/session setup.

Uses SQLite for the prototype (zero-setup, file-based, still gives us
real transactions). PostgreSQL would be the production choice -- the
only change needed is DATABASE_URL, since all queries go through
SQLAlchemy Core/ORM and the atomic-update pattern used for agent/borrower
reservation (UPDATE ... WHERE state = 'AVAILABLE') works identically on
both engines.
"""
import os
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = os.environ.get("SMARTDIALER_DATABASE_URL", "sqlite:///./smartdialer.db")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

Base = declarative_base()


def init_db():
    # Import models so they're registered on Base.metadata before create_all.
    from . import models  # noqa: F401

    Base.metadata.create_all(bind=engine)


def get_db():
    """FastAPI dependency: yields a session, always closed after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope():
    """Context manager for use outside of FastAPI request handling (services, tests)."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
