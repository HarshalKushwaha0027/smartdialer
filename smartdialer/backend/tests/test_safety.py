"""
Covers:
  - Predictive pacing math.
  - Safety Controller never approves more than safe capacity.
  - Scenario: provider outage -> forced Progressive Mode.
  - Scenario: agent availability drops between proposal and approval.
"""
from backend.services import predictive_engine, safety_controller, agent_manager
from backend.models import AgentState
from .conftest import make_agents


def test_predictive_engine_basic_formula():
    proposal = predictive_engine.propose_call_count(
        predictive_engine.PacingInputs(available_agents=10, answer_rate=0.5)
    )
    assert proposal.proposed_calls == 20  # floor(10 / 0.5)


def test_predictive_engine_zero_agents():
    proposal = predictive_engine.propose_call_count(
        predictive_engine.PacingInputs(available_agents=0, answer_rate=0.5)
    )
    assert proposal.proposed_calls == 0


def test_safety_controller_never_exceeds_available_agents(db):
    make_agents(db, 10)
    decision = safety_controller.evaluate(db, proposed_calls=20, mode="predictive", answer_rate=0.5)
    assert decision.approved_calls == 10  # clamped to actual available agents
    assert decision.approved_calls <= agent_manager.count_available(db)


def test_safety_controller_approves_in_full_when_safe(db):
    make_agents(db, 10)
    decision = safety_controller.evaluate(db, proposed_calls=5, mode="predictive", answer_rate=0.5)
    assert decision.approved_calls == 5


def test_safety_controller_accounts_for_already_active_calls(db):
    agents = make_agents(db, 10)
    # Reserve 4 of them already (simulating in-flight calls).
    for a in agents[:4]:
        agent_manager.try_reserve_agent(db, a.id)

    decision = safety_controller.evaluate(db, proposed_calls=20, mode="predictive", answer_rate=0.5)
    # 10 agents total, 4 already RESERVED (active): available=6, active=4
    # -> safe_capacity = available - active = 2 (the system is already half
    # committed, so only 2 MORE calls can safely be started on top of that).
    assert decision.approved_calls == 2


def test_provider_outage_forces_progressive_mode(db):
    make_agents(db, 10)
    proposal = predictive_engine.propose_call_count(
        predictive_engine.PacingInputs(available_agents=10, answer_rate=0.5, provider_health=0.1)
    )
    decision = safety_controller.evaluate(
        db, proposed_calls=proposal.proposed_calls, mode="predictive", answer_rate=0.5, provider_health=0.1
    )
    assert decision.forced_progressive is True
    assert decision.approved_calls <= 1


def test_agent_dropout_between_proposal_and_approval_is_respected(db):
    agents = make_agents(db, 10)
    stale_available = agent_manager.count_available(db)  # 10

    # Availability suddenly drops: 6 agents go PAUSED after the proposal
    # was computed but before the safety controller runs.
    for a in agents[:6]:
        agent_manager.set_agent_state(db, a.id, AgentState.PAUSED)

    proposal = predictive_engine.propose_call_count(
        predictive_engine.PacingInputs(available_agents=stale_available, answer_rate=0.5)
    )  # proposes 20, based on stale count of 10

    decision = safety_controller.evaluate(
        db, proposed_calls=proposal.proposed_calls, mode="predictive", answer_rate=0.5
    )
    # Only 4 agents are actually available now -> must clamp to 4, not 20 or 10.
    assert decision.approved_calls == 4
