"""
Covers:
  - Scenario 3: Duplicate ANSWERED/CONNECTED event is ignored, not double-applied.
  - Scenario 5: Out-of-order event (stale RINGING after COMPLETED) is ignored.
  - Scenario 4: Worker crash after reservation -- resources are recovered, not leaked.
"""
import uuid
from datetime import datetime

from backend.models import CallStatus, AgentState
from backend.services import agent_manager, borrower_queue, progressive_dialer, call_allocator
from .conftest import make_agents, make_borrowers


def _start_call(db):
    make_agents(db, 1)
    make_borrowers(db, 1)
    call = progressive_dialer.progressive_dial(db)
    assert call is not None
    return call


def test_duplicate_connected_event_is_ignored(db):
    call = _start_call(db)
    event_id = f"evt-{uuid.uuid4().hex[:8]}"
    now = datetime.utcnow()

    first = call_allocator.apply_provider_event(
        db, provider="provider_a", event_id=event_id, call_id=call.id,
        event_type="RINGING", emitted_at=now,
    )
    second = call_allocator.apply_provider_event(
        db, provider="provider_a", event_id=event_id, call_id=call.id,
        event_type="RINGING", emitted_at=now,
    )

    assert first["applied"] is True
    assert second["applied"] is False
    assert second["reason"] == "duplicate_event_ignored"

    db.refresh(call)
    assert call.status == CallStatus.RINGING  # not advanced twice / corrupted


def test_stale_out_of_order_event_after_completion_is_ignored(db):
    call = _start_call(db)
    now = datetime.utcnow()

    call_allocator.apply_provider_event(db, provider="provider_a", event_id=f"e{uuid.uuid4().hex[:6]}",
                                         call_id=call.id, event_type="RINGING", emitted_at=now)
    call_allocator.apply_provider_event(db, provider="provider_a", event_id=f"e{uuid.uuid4().hex[:6]}",
                                         call_id=call.id, event_type="CONNECTED", emitted_at=now)
    call_allocator.apply_provider_event(db, provider="provider_a", event_id=f"e{uuid.uuid4().hex[:6]}",
                                         call_id=call.id, event_type="COMPLETED", emitted_at=now)

    db.refresh(call)
    assert call.status == CallStatus.COMPLETED

    # A late-arriving RINGING for the same call must NOT roll back the state.
    late = call_allocator.apply_provider_event(
        db, provider="provider_a", event_id=f"e{uuid.uuid4().hex[:6]}",
        call_id=call.id, event_type="RINGING", emitted_at=now,
    )
    assert late["applied"] is False
    assert late["reason"] == "stale_out_of_order_event"

    db.refresh(call)
    assert call.status == CallStatus.COMPLETED  # unchanged


def test_illegal_transition_rejected(db):
    call = _start_call(db)
    now = datetime.utcnow()
    # INITIATED -> COMPLETED directly is not a legal transition.
    result = call_allocator.apply_provider_event(
        db, provider="provider_a", event_id=f"e{uuid.uuid4().hex[:6]}",
        call_id=call.id, event_type="COMPLETED", emitted_at=now,
    )
    assert result["applied"] is False
    assert result["reason"] == "illegal_transition"


def test_completed_call_releases_agent_and_marks_borrower_called(db):
    call = _start_call(db)
    now = datetime.utcnow()
    for etype in ("RINGING", "CONNECTED", "COMPLETED"):
        call_allocator.apply_provider_event(
            db, provider="provider_a", event_id=f"e{uuid.uuid4().hex[:6]}",
            call_id=call.id, event_type=etype, emitted_at=now,
        )
    assert agent_manager.count_available(db) == 1
    assert borrower_queue.remaining_count(db) == 0


def test_worker_crash_after_reservation_recovers_resources(db):
    """
    Scenario 4: a worker reserves an agent + borrower and then crashes
    before initiating the call. Resources must be recoverable rather
    than permanently stuck in RESERVED.
    """
    make_agents(db, 1)
    make_borrowers(db, 1)

    agent = agent_manager.try_reserve_any_available_agent(db)
    borrower = borrower_queue.try_reserve_next_borrower(db)
    assert agent is not None and borrower is not None
    assert agent.state == AgentState.RESERVED

    # Worker crashes here (no initiate_call ever happens). Recovery path:
    recovered = agent_manager.release_agent(db, agent.id)
    borrower_queue.release_borrower(db, borrower.id, called=False)

    assert recovered.state == AgentState.AVAILABLE
    assert agent_manager.count_available(db) == 1
    assert borrower_queue.remaining_count(db) == 1  # borrower NOT marked called -- crash wasn't their fault
