"""
Call Allocator.

Responsible for:
  1. Turning a (reserved agent, reserved borrower) pair into an actual
     Call row + a provider dial attempt.
  2. Processing inbound provider events IDEMPOTENTLY and only applying
     legal, non-stale state transitions (out-of-order protection).

Idempotency: every inbound event carries a provider-issued event_id. We
try to INSERT it into provider_events under a UNIQUE(provider, event_id)
constraint first. If that insert is rejected (IntegrityError), the event
is a duplicate -- we stop immediately and never touch the Call row twice.

Out-of-order protection: even a *first-seen* event can be stale, e.g. a
retried "RINGING" notification that physically arrives after we've
already processed "COMPLETED". We use CALL_STATUS_RANK to detect that
the event's rank is <= the call's current rank and ignore it rather than
regress the call's state.
"""
from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import Call, CallStatus, CALL_TRANSITIONS, CALL_STATUS_RANK, ProviderEvent, AgentState
from . import agent_manager, borrower_queue


def initiate_call(db: Session, *, agent_id: str, borrower_id: str, provider: str, mode: str) -> Call:
    """
    Precondition: caller has ALREADY atomically reserved both the agent
    (AVAILABLE -> RESERVED) and the borrower before calling this.
    """
    call = Call(agent_id=agent_id, borrower_id=borrower_id, provider=provider, mode=mode,
                status=CallStatus.INITIATED)
    db.add(call)
    db.commit()
    db.refresh(call)

    agent_manager.set_agent_state(db, agent_id, AgentState.DIALING, call_id=call.id)
    return call


def apply_provider_event(db: Session, *, provider: str, event_id: str, call_id: str,
                          event_type: str, emitted_at: datetime) -> dict:
    """
    Returns a small dict describing what happened, used by the API layer
    and tests: {"applied": bool, "reason": str}.
    """
    # 1) Idempotency check -- try to claim this event_id first.
    record = ProviderEvent(
        provider=provider, event_id=event_id, call_id=call_id,
        event_type=CallStatus(event_type), emitted_at=emitted_at, applied=False,
    )
    db.add(record)
    try:
        db.flush()  # triggers the UNIQUE constraint check without a full commit
    except IntegrityError:
        db.rollback()
        return {"applied": False, "reason": "duplicate_event_ignored"}

    call = db.get(Call, call_id)
    if call is None:
        record.ignore_reason = "unknown_call"
        db.commit()
        return {"applied": False, "reason": "unknown_call"}

    target = CallStatus(event_type)

    # 2) Out-of-order check -- is this event stale relative to where the
    #    call already is?
    if CALL_STATUS_RANK[target] <= CALL_STATUS_RANK[call.status] and target != call.status:
        record.ignore_reason = "stale_out_of_order_event"
        db.commit()
        return {"applied": False, "reason": "stale_out_of_order_event"}
    if target == call.status:
        record.ignore_reason = "no_op_same_state"
        db.commit()
        return {"applied": False, "reason": "no_op_same_state"}

    # 3) Legality check -- is this a transition the state machine allows?
    if target not in CALL_TRANSITIONS.get(call.status, set()):
        record.ignore_reason = "illegal_transition"
        db.commit()
        return {"applied": False, "reason": "illegal_transition"}

    # 4) Apply.
    call.status = target
    record.applied = True
    db.commit()

    _sync_agent_and_borrower(db, call)
    return {"applied": True, "reason": "ok"}


def _sync_agent_and_borrower(db: Session, call: Call) -> None:
    """Keep agent/borrower state in lockstep with the call's state."""
    if call.status == CallStatus.CONNECTED:
        agent_manager.set_agent_state(db, call.agent_id, AgentState.CONNECTED)
    elif call.status == CallStatus.COMPLETED:
        agent_manager.set_agent_state(db, call.agent_id, AgentState.WRAP_UP)
        agent_manager.release_agent(db, call.agent_id)
        borrower_queue.release_borrower(db, call.borrower_id, called=True)
    elif call.status == CallStatus.FAILED:
        agent_manager.release_agent(db, call.agent_id)
        # A failed *attempt* still counts as having tried this borrower.
        borrower_queue.release_borrower(db, call.borrower_id, called=True)


def timeout_stale_calls(db: Session, older_than_seconds: int = 30) -> int:
    """
    Failure-handling demo: a provider timeout (no events ever arrive).
    Any call still INITIATED/RINGING past the timeout window is forced
    to FAILED and its resources released. Returns how many were reaped.
    """
    from datetime import timedelta
    cutoff = datetime.utcnow() - timedelta(seconds=older_than_seconds)
    stale = (
        db.query(Call)
        .filter(Call.status.in_([CallStatus.INITIATED, CallStatus.RINGING]), Call.updated_at < cutoff)
        .all()
    )
    for call in stale:
        call.status = CallStatus.FAILED
        db.commit()
        agent_manager.release_agent(db, call.agent_id)
        borrower_queue.release_borrower(db, call.borrower_id, called=True)
    return len(stale)
