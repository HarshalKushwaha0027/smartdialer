import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import Base
from backend import models  # noqa: F401 -- register models on Base.metadata


@pytest.fixture()
def db():
    """Fresh in-memory SQLite DB per test, fully isolated."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, future=True)
    session = TestSession()
    try:
        yield session
    finally:
        session.close()


def make_agents(db, n, state=None):
    from backend.models import Agent, AgentState
    agents = []
    for i in range(n):
        a = Agent(name=f"A{i}", state=state or AgentState.AVAILABLE)
        db.add(a)
        agents.append(a)
    db.commit()
    for a in agents:
        db.refresh(a)
    return agents


def make_borrowers(db, n):
    from backend.models import Borrower
    borrowers = []
    for i in range(n):
        b = Borrower(name=f"B{i}", phone=f"+1-555-{i:04d}")
        db.add(b)
        borrowers.append(b)
    db.commit()
    for b in borrowers:
        db.refresh(b)
    return borrowers
