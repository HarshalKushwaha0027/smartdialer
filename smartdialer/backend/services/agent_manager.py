"""
Agent Management.

The key correctness property this module provides is ATOMIC RESERVATION:
when two concurrent workers both try to grab the same AVAILABLE agent,
exactly one of them must succeed. We get this without SELECT ... FOR
UPDATE (which SQLite doesn't support) by issuing a single conditional
UPDATE statement:

    UPDATE agents SET state = 'RESERVED' WHERE id = :id AND state = 'AVAILABLE'

and checking the number of rows the UPDATE actually touched. A relational
database guarantees that statement itself is atomic, so only one of the
two concurrent UPDATEs can see state == 'AVAILABLE' and flip it. The
loser's UPDATE matches zero rows and is told so (rowcount == 0) -- it
never silently "succeeds" twice.

This is also exactly how production systems do optimistic, lock-free
concurrency control at the database layer, and it would carry over to
PostgreSQL unchanged.
"""
from sqlalchemy import update
from sqlalchemy.orm import Session

from ..models import Agent, AgentState, AGENT_TRANSITIONS


class InvalidTransitionError(Exception):
    pass


def validate_transition(current: AgentState, target: AgentState) -> None:
    if target not in AGENT_TRANSITIONS.get(current, set()):
        raise InvalidTransitionError(f"Agent cannot go {current} -> {target}")


def try_reserve_agent(db: Session, agent_id: str) -> bool:
    """
    Atomically flips one agent AVAILABLE -> RESERVED.
    Returns True iff THIS caller won the race.
    """
    result = db.execute(
        update(Agent)
        .where(Agent.id == agent_id, Agent.state == AgentState.AVAILABLE)
        .values(state=AgentState.RESERVED)
    )
    db.commit()
    return result.rowcount == 1


def try_reserve_any_available_agent(db: Session) -> Agent | None:
    """
    Picks one AVAILABLE agent and atomically reserves it. Instead of
    SELECT-then-UPDATE (which has a race between the two statements),
    we select a *candidate* id and then attempt the same conditional
    UPDATE above; if we lose the race we just try the next candidate.
    """
    candidates = (
        db.query(Agent.id)
        .filter(Agent.state == AgentState.AVAILABLE)
        .order_by(Agent.updated_at.asc())
        .limit(25)
        .all()
    )
    for (agent_id,) in candidates:
        if try_reserve_agent(db, agent_id):
            return db.get(Agent, agent_id)
    return None


def set_agent_state(db: Session, agent_id: str, target: AgentState, *, call_id: str | None = None) -> Agent:
    agent = db.get(Agent, agent_id)
    if agent is None:
        raise ValueError(f"Unknown agent {agent_id}")
    validate_transition(agent.state, target)
    agent.state = target
    if call_id is not None:
        agent.current_call_id = call_id
    db.commit()
    db.refresh(agent)
    return agent


def release_agent(db: Session, agent_id: str) -> Agent:
    """Return an agent to AVAILABLE after wrap-up (or a failed dial attempt)."""
    agent = db.get(Agent, agent_id)
    if agent is None:
        raise ValueError(f"Unknown agent {agent_id}")
    if agent.state in (AgentState.RESERVED, AgentState.DIALING, AgentState.WRAP_UP):
        agent.state = AgentState.AVAILABLE
        agent.current_call_id = None
        db.commit()
        db.refresh(agent)
    return agent


def count_available(db: Session) -> int:
    return db.query(Agent).filter(Agent.state == AgentState.AVAILABLE).count()


def count_active(db: Session) -> int:
    """Agents currently tied up in some phase of a call."""
    return (
        db.query(Agent)
        .filter(Agent.state.in_([AgentState.RESERVED, AgentState.DIALING, AgentState.CONNECTED, AgentState.WRAP_UP]))
        .count()
    )
