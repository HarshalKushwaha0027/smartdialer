"""
Progressive Dialer.

The guaranteed fallback mode. Finds one available agent, reserves it,
reserves one borrower, and starts exactly one call. If either
reservation fails (lost the race, or queue empty) it cleanly releases
whatever it already grabbed and returns None -- no resource leak.
"""
from sqlalchemy.orm import Session

from ..models import Call
from . import agent_manager, borrower_queue, call_allocator


def progressive_dial(db: Session, *, provider: str = "provider_a") -> Call | None:
    agent = agent_manager.try_reserve_any_available_agent(db)
    if agent is None:
        return None

    borrower = borrower_queue.try_reserve_next_borrower(db)
    if borrower is None:
        agent_manager.release_agent(db, agent.id)
        return None

    return call_allocator.initiate_call(
        db, agent_id=agent.id, borrower_id=borrower.id, provider=provider, mode="progressive"
    )
