"""
ORM models + state machines.

State machines are defined here (not just in services) so that both the
DB layer and the services agree on what a "legal" transition is. This is
what lets us reject a late RINGING event that arrives after a call has
already reached COMPLETED (out-of-order event handling).
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Column, String, Integer, Float, DateTime, ForeignKey, Enum as SAEnum, Boolean, UniqueConstraint
)
from sqlalchemy.orm import relationship

from .database import Base


def gen_id() -> str:
    return uuid.uuid4().hex[:12]


# --------------------------------------------------------------------------
# Agent state machine
# --------------------------------------------------------------------------
class AgentState(str, enum.Enum):
    OFFLINE = "OFFLINE"
    AVAILABLE = "AVAILABLE"
    RESERVED = "RESERVED"
    DIALING = "DIALING"
    CONNECTED = "CONNECTED"
    WRAP_UP = "WRAP_UP"
    PAUSED = "PAUSED"


# Legal transitions for an agent. Anything not listed here is rejected.
AGENT_TRANSITIONS = {
    AgentState.OFFLINE: {AgentState.AVAILABLE},
    AgentState.AVAILABLE: {AgentState.RESERVED, AgentState.PAUSED, AgentState.OFFLINE},
    AgentState.RESERVED: {AgentState.DIALING, AgentState.AVAILABLE},  # back to AVAILABLE = reservation released
    AgentState.DIALING: {AgentState.CONNECTED, AgentState.AVAILABLE},  # AVAILABLE = call failed to connect
    AgentState.CONNECTED: {AgentState.WRAP_UP},
    AgentState.WRAP_UP: {AgentState.AVAILABLE, AgentState.OFFLINE, AgentState.PAUSED},
    AgentState.PAUSED: {AgentState.AVAILABLE, AgentState.OFFLINE},
}


class Agent(Base):
    __tablename__ = "agents"

    id = Column(String, primary_key=True, default=gen_id)
    name = Column(String, nullable=False)
    state = Column(SAEnum(AgentState), nullable=False, default=AgentState.OFFLINE)
    current_call_id = Column(String, ForeignKey("calls.id"), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    calls = relationship("Call", back_populates="agent", foreign_keys="Call.agent_id")


# --------------------------------------------------------------------------
# Borrower
# --------------------------------------------------------------------------
class Borrower(Base):
    __tablename__ = "borrowers"

    id = Column(String, primary_key=True, default=gen_id)
    name = Column(String, nullable=False)
    phone = Column(String, nullable=False)
    reserved = Column(Boolean, default=False)      # currently part of an in-flight call
    already_called = Column(Boolean, default=False)  # terminal: never call again
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    calls = relationship("Call", back_populates="borrower")


# --------------------------------------------------------------------------
# Call state machine
# --------------------------------------------------------------------------
class CallStatus(str, enum.Enum):
    INITIATED = "INITIATED"
    RINGING = "RINGING"
    CONNECTED = "CONNECTED"
    FAILED = "FAILED"
    COMPLETED = "COMPLETED"


CALL_TRANSITIONS = {
    CallStatus.INITIATED: {CallStatus.RINGING, CallStatus.FAILED},
    CallStatus.RINGING: {CallStatus.CONNECTED, CallStatus.FAILED},
    CallStatus.CONNECTED: {CallStatus.COMPLETED, CallStatus.FAILED},
    CallStatus.FAILED: set(),      # terminal
    CallStatus.COMPLETED: set(),   # terminal
}

# Rank used to detect "out-of-order": an event for an earlier state than
# the call's current state is stale and must be dropped.
CALL_STATUS_RANK = {
    CallStatus.INITIATED: 0,
    CallStatus.RINGING: 1,
    CallStatus.CONNECTED: 2,
    CallStatus.COMPLETED: 3,
    CallStatus.FAILED: 3,  # terminal, same rank as COMPLETED
}


class Call(Base):
    __tablename__ = "calls"

    id = Column(String, primary_key=True, default=gen_id)
    agent_id = Column(String, ForeignKey("agents.id"), nullable=False)
    borrower_id = Column(String, ForeignKey("borrowers.id"), nullable=False)
    provider = Column(String, nullable=False)  # "provider_a" | "provider_b"
    mode = Column(String, nullable=False)      # "progressive" | "predictive"
    status = Column(SAEnum(CallStatus), nullable=False, default=CallStatus.INITIATED)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    agent = relationship("Agent", back_populates="calls", foreign_keys=[agent_id])
    borrower = relationship("Borrower", back_populates="calls")


# --------------------------------------------------------------------------
# Provider events (idempotency ledger)
# --------------------------------------------------------------------------
class ProviderEvent(Base):
    """
    Every inbound provider event is recorded by its provider-issued event id.
    A UNIQUE constraint on (provider, event_id) is what gives us idempotency:
    a duplicate insert fails at the DB level and is treated as "already
    processed" rather than applied twice.
    """
    __tablename__ = "provider_events"
    __table_args__ = (UniqueConstraint("provider", "event_id", name="uq_provider_event"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    provider = Column(String, nullable=False)
    event_id = Column(String, nullable=False)       # provider-issued, may arrive >1 time
    call_id = Column(String, ForeignKey("calls.id"), nullable=False)
    event_type = Column(SAEnum(CallStatus), nullable=False)
    emitted_at = Column(DateTime, nullable=False)    # when the provider says it happened
    received_at = Column(DateTime, default=datetime.utcnow)  # when we actually got it
    applied = Column(Boolean, default=False)         # False => duplicate or stale, ignored
    ignore_reason = Column(String, nullable=True)


# --------------------------------------------------------------------------
# Pacing / safety decision log (drives the "Recent system decisions" panel)
# --------------------------------------------------------------------------
class PacingDecision(Base):
    __tablename__ = "pacing_decisions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    mode = Column(String, nullable=False)
    available_agents = Column(Integer, nullable=False)
    answer_rate = Column(Float, nullable=False)
    proposed_calls = Column(Integer, nullable=False)
    approved_calls = Column(Integer, nullable=False)
    reason = Column(String, nullable=False)
