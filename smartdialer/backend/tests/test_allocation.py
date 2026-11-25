"""
Covers:
  - Scenario 1: Two workers try to reserve the same agent -> exactly one wins.
  - Progressive dialer happy path and empty-queue path.
  - Borrower is never called twice.
"""
from backend.services import agent_manager, borrower_queue, progressive_dialer
from backend.models import AgentState
from .conftest import make_agents, make_borrowers


def test_two_workers_cannot_reserve_same_agent(db):
    [agent] = make_agents(db, 1)

    # Simulate two concurrent workers racing for the SAME agent id.
    worker_1_won = agent_manager.try_reserve_agent(db, agent.id)
    worker_2_won = agent_manager.try_reserve_agent(db, agent.id)

    assert worker_1_won is True
    assert worker_2_won is False  # second worker must lose the race, not double-reserve

    db.refresh(agent)
    assert agent.state == AgentState.RESERVED


def test_reserve_any_available_picks_distinct_agents_under_contention(db):
    make_agents(db, 5)

    reserved_ids = set()
    for _ in range(5):
        agent = agent_manager.try_reserve_any_available_agent(db)
        assert agent is not None
        reserved_ids.add(agent.id)

    assert len(reserved_ids) == 5  # no agent handed out twice

    # A 6th attempt must fail -- no agents left.
    assert agent_manager.try_reserve_any_available_agent(db) is None


def test_progressive_dial_happy_path(db):
    make_agents(db, 1)
    make_borrowers(db, 1)

    call = progressive_dialer.progressive_dial(db)
    assert call is not None
    assert call.mode == "progressive"

    # Agent should now be DIALING, borrower reserved.
    db.refresh(call)
    assert agent_manager.count_available(db) == 0


def test_progressive_dial_returns_none_when_no_agents(db):
    make_borrowers(db, 1)
    assert progressive_dialer.progressive_dial(db) is None


def test_progressive_dial_releases_agent_when_no_borrowers(db):
    make_agents(db, 1)
    # No borrowers seeded.
    call = progressive_dialer.progressive_dial(db)
    assert call is None
    # The agent reservation must have been rolled back, not leaked.
    assert agent_manager.count_available(db) == 1


def test_borrower_never_dialed_twice(db):
    make_agents(db, 3)
    make_borrowers(db, 1)

    first = progressive_dialer.progressive_dial(db)
    assert first is not None

    # Even though agents remain available, the single borrower is now
    # reserved (mid-call) and must not be handed out again.
    second = progressive_dialer.progressive_dial(db)
    assert second is None
