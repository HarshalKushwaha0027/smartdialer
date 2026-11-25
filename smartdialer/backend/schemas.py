from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class AgentOut(BaseModel):
    id: str
    name: str
    state: str

    class Config:
        from_attributes = True


class BorrowerOut(BaseModel):
    id: str
    name: str
    phone: str
    reserved: bool
    already_called: bool

    class Config:
        from_attributes = True


class CallOut(BaseModel):
    id: str
    agent_id: str
    borrower_id: str
    provider: str
    mode: str
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class PacingDecisionOut(BaseModel):
    id: int
    created_at: datetime
    mode: str
    available_agents: int
    answer_rate: float
    proposed_calls: int
    approved_calls: int
    reason: str

    class Config:
        from_attributes = True


class SeedRequest(BaseModel):
    num_agents: int = Field(10, ge=0, le=200)
    num_borrowers: int = Field(100, ge=0, le=5000)


class TickRequest(BaseModel):
    mode: str = Field("predictive", pattern="^(progressive|predictive)$")
    provider: str = Field("provider_a", pattern="^(provider_a|provider_b)$")
    answer_rate: float = Field(0.5, gt=0.0, le=1.0)


class ProviderEventIn(BaseModel):
    """What a (mock) telecom provider sends us about a call."""
    provider: str
    event_id: str
    call_id: str
    event_type: str  # RINGING | CONNECTED | FAILED | COMPLETED
    emitted_at: datetime


class DashboardOut(BaseModel):
    agents_total: int
    agents_available: int
    agents_active: int
    borrowers_remaining: int
    calls_initiated: int
    calls_connected: int
    calls_failed: int
    calls_completed: int
    utilization: float
    recent_decisions: list[PacingDecisionOut]
    recent_calls: list[CallOut]
    agents: list[AgentOut]
