"""
Predictive Pacing Engine.

Proposes how many calls COULD be started based on available agents and
the expected answer rate:

    proposed = floor(available_agents / answer_rate)

This is intentionally the simple, explainable statistical model the
assignment asks for (not an ML model). Historical answer rate, average
call duration and provider health are accepted as inputs so the formula
can be extended, but the core idea -- "if only half of calls get
answered, dial roughly twice as many as we have agents for" -- stays the
same.

CRITICAL: this module NEVER initiates a call. It only proposes a number.
The Safety Controller has the only authority to approve/reduce it and
the only authority to initiate calls off a predictive decision.
"""
import math
from dataclasses import dataclass


@dataclass
class PacingInputs:
    available_agents: int
    answer_rate: float            # 0 < rate <= 1
    currently_ringing: int = 0
    provider_health: float = 1.0  # 1.0 = fully healthy, 0.0 = provider down


@dataclass
class PacingProposal:
    proposed_calls: int
    rationale: str


def propose_call_count(inputs: PacingInputs) -> PacingProposal:
    if inputs.available_agents <= 0:
        return PacingProposal(0, "no agents available")

    rate = max(inputs.answer_rate, 0.01)  # guard against divide-by-near-zero
    raw = math.floor(inputs.available_agents / rate)

    # Provider health degrades the proposal linearly; a dead provider (0.0)
    # collapses the proposal to 0, which is what lets the Safety Controller
    # force Progressive Mode (see safety_controller.should_force_progressive).
    health_adjusted = math.floor(raw * inputs.provider_health)

    # Already-ringing calls are capacity already committed; don't propose
    # starting more on top of them.
    net_proposal = max(0, health_adjusted - inputs.currently_ringing)

    return PacingProposal(
        proposed_calls=net_proposal,
        rationale=(
            f"available_agents={inputs.available_agents}, answer_rate={rate:.2f}, "
            f"raw=floor({inputs.available_agents}/{rate:.2f})={raw}, "
            f"provider_health={inputs.provider_health:.2f} -> health_adjusted={health_adjusted}, "
            f"currently_ringing={inputs.currently_ringing} -> net={net_proposal}"
        ),
    )
