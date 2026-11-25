"""
Safety Controller -- the highest-priority component.

Takes the Predictive Pacing Engine's PROPOSAL and the real-time system
state, and returns the number of calls that may ACTUALLY be initiated
this tick. It is the only component allowed to turn a predictive
proposal into real dial attempts.

Guarantee: approved_calls can never exceed the number of agents that
are genuinely AVAILABLE right now. This is enforced twice: once here as
a capacity cap, and a second time structurally, because every approved
"slot" is consumed by calling progressive_dial() once per slot, and
progressive_dial() itself atomically reserves one agent per call -- so
even if this cap were wrong, the atomic reservation in agent_manager
cannot be bypassed and no agent can ever be double-booked.

For the one-hour prototype we use a STRICT one-agent-per-outstanding-call
rule (safe_capacity = available - active). Production systems allow a
bounded amount of controlled over-dialing (dialing slightly ahead of
confirmed availability, within a mathematically defined answer-risk
budget) to raise utilization, but that budget must still be capped by a
deterministic guard identical in spirit to this one. We do not implement
over-dialing here: it adds risk without adding evaluation value for a
one-hour prototype, and the assignment explicitly separates pacing from
safety so this guard stays simple and auditable.
"""
from dataclasses import dataclass

from sqlalchemy.orm import Session

from ..models import PacingDecision
from . import agent_manager


@dataclass
class SafetyDecision:
    approved_calls: int
    reason: str
    forced_progressive: bool = False


PROVIDER_HEALTH_FORCE_THRESHOLD = 0.4


def should_force_progressive(provider_health: float) -> bool:
    return provider_health < PROVIDER_HEALTH_FORCE_THRESHOLD


def evaluate(db: Session, *, proposed_calls: int, mode: str, answer_rate: float,
             provider_health: float = 1.0) -> SafetyDecision:
    available = agent_manager.count_available(db)
    active = agent_manager.count_active(db)
    safe_capacity = max(0, available - active)

    forced = False
    if mode == "predictive" and should_force_progressive(provider_health):
        # Provider is degraded enough that we no longer trust bulk predictive
        # dialing: fall back to one call at a time regardless of what the
        # pacing engine proposed.
        approved = min(1, safe_capacity)
        forced = True
        reason = (
            f"provider_health={provider_health:.2f} below threshold "
            f"{PROVIDER_HEALTH_FORCE_THRESHOLD} -> forced Progressive Mode, approved={approved}"
        )
    else:
        approved = min(proposed_calls, safe_capacity)
        if approved < proposed_calls:
            reason = f"reduced: proposed={proposed_calls} > safe_capacity={safe_capacity} (available={available}, active={active})"
        else:
            reason = f"approved in full: proposed={proposed_calls} <= safe_capacity={safe_capacity}"

    decision = PacingDecision(
        mode=mode,
        available_agents=available,
        answer_rate=answer_rate,
        proposed_calls=proposed_calls,
        approved_calls=approved,
        reason=reason,
    )
    db.add(decision)
    db.commit()

    return SafetyDecision(approved_calls=approved, reason=reason, forced_progressive=forced)
