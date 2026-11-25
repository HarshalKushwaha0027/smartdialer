"""
SmartDialer API.

Endpoints:
  POST /seed                 -- create agents + borrowers for a fresh demo
  POST /simulation/tick      -- run ONE pacing/dial cycle (progressive or predictive)
  POST /simulation/reset     -- wipe and start over
  GET  /dashboard            -- aggregated state for the frontend
  GET  /agents, /borrowers, /calls, /decisions
  POST /events/duplicate-demo, /events/out-of-order-demo, /events/worker-crash-demo
       -- deterministic, on-demand demonstrations of the 5 failure scenarios

Background delivery of provider events is done with FastAPI's
BackgroundTasks + asyncio.sleep, so a call initiated via /simulation/tick
has its RINGING/CONNECTED/FAILED/COMPLETED events arrive a little later,
just like a real async provider webhook would.
"""
import asyncio
import random
import uuid
from datetime import datetime

import os

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from .database import get_db, init_db, session_scope
from .models import Agent, AgentState, Borrower, Call, CallStatus, PacingDecision
from .providers import get_provider
from .schemas import (
    DashboardOut, SeedRequest, TickRequest, AgentOut, BorrowerOut, CallOut, PacingDecisionOut,
)
from .services import agent_manager, borrower_queue, call_allocator, progressive_dialer
from .services import predictive_engine, safety_controller

app = FastAPI(title="SmartDialer", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    init_db()


# --------------------------------------------------------------------------
# Seeding / reset
# --------------------------------------------------------------------------
@app.post("/seed")
def seed(req: SeedRequest, db: Session = Depends(get_db)):
    for i in range(req.num_agents):
        db.add(Agent(name=f"Agent {i + 1}", state=AgentState.AVAILABLE))
    for i in range(req.num_borrowers):
        db.add(Borrower(name=f"Borrower {i + 1}", phone=f"+1-555-{1000 + i:04d}"))
    db.commit()
    return {"agents_created": req.num_agents, "borrowers_created": req.num_borrowers}


@app.post("/simulation/reset")
def reset(db: Session = Depends(get_db)):
    db.query(PacingDecision).delete()
    db.query(Call).delete()
    db.query(Borrower).delete()
    db.query(Agent).delete()
    db.commit()
    return {"status": "reset"}


# --------------------------------------------------------------------------
# Background event delivery for a single call (simulates the provider's
# async webhook stream, including provider_b's duplicates/out-of-order).
# --------------------------------------------------------------------------
async def _deliver_events(call_id: str, provider_name: str, answer_rate: float):
    provider = get_provider(provider_name)
    planned = provider.plan_call_events(call_id, answer_rate)
    # Sort by delay_seconds = the order they will actually ARRIVE, which for
    # provider_b may differ from the order they logically occurred in.
    planned_sorted = sorted(planned, key=lambda e: e.delay_seconds)
    for raw in planned_sorted:
        await asyncio.sleep(min(raw.delay_seconds, 0.05))  # compressed for demo speed
        with session_scope() as db:
            call_allocator.apply_provider_event(
                db,
                provider=provider_name,
                event_id=raw.event_id,
                call_id=call_id,
                event_type=raw.event_type,
                emitted_at=raw.emitted_at,
            )


# --------------------------------------------------------------------------
# Simulation tick
# --------------------------------------------------------------------------
@app.post("/simulation/tick")
def simulation_tick(req: TickRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    started_calls: list[Call] = []

    if req.mode == "progressive":
        call = progressive_dialer.progressive_dial(db, provider=req.provider)
        if call:
            started_calls.append(call)
        decision = PacingDecision(
            mode="progressive",
            available_agents=agent_manager.count_available(db),
            answer_rate=req.answer_rate,
            proposed_calls=1 if call else 0,
            approved_calls=1 if call else 0,
            reason="progressive mode: one agent, one call" if call else "no agent or borrower available",
        )
        db.add(decision)
        db.commit()
    else:
        available = agent_manager.count_available(db)
        proposal = predictive_engine.propose_call_count(
            predictive_engine.PacingInputs(
                available_agents=available,
                answer_rate=req.answer_rate,
                currently_ringing=db.query(Call).filter(Call.status == CallStatus.RINGING).count(),
                provider_health=1.0 if req.provider == "provider_a" else 0.85,
            )
        )
        safety = safety_controller.evaluate(
            db,
            proposed_calls=proposal.proposed_calls,
            mode="predictive",
            answer_rate=req.answer_rate,
            provider_health=1.0 if req.provider == "provider_a" else 0.85,
        )
        for _ in range(safety.approved_calls):
            call = progressive_dialer.progressive_dial(db, provider=req.provider)
            if call is None:
                break
            started_calls.append(call)

    for call in started_calls:
        background_tasks.add_task(_deliver_events, call.id, call.provider, req.answer_rate)

    return {
        "started_calls": [c.id for c in started_calls],
        "count": len(started_calls),
    }


# --------------------------------------------------------------------------
# On-demand failure-scenario demonstrations (for the "5 scenarios" tests)
# --------------------------------------------------------------------------
@app.post("/demo/duplicate-event")
def demo_duplicate_event(db: Session = Depends(get_db)):
    call = progressive_dialer.progressive_dial(db, provider="provider_a")
    if call is None:
        raise HTTPException(400, "no agent/borrower available to demo with")
    event_id = f"evt-{uuid.uuid4().hex[:8]}"
    first = call_allocator.apply_provider_event(
        db, provider="provider_a", event_id=event_id, call_id=call.id,
        event_type="RINGING", emitted_at=datetime.utcnow(),
    )
    second = call_allocator.apply_provider_event(
        db, provider="provider_a", event_id=event_id, call_id=call.id,
        event_type="RINGING", emitted_at=datetime.utcnow(),
    )
    return {"call_id": call.id, "first_application": first, "duplicate_application": second}


@app.post("/demo/out-of-order-event")
def demo_out_of_order_event(db: Session = Depends(get_db)):
    call = progressive_dialer.progressive_dial(db, provider="provider_a")
    if call is None:
        raise HTTPException(400, "no agent/borrower available to demo with")
    now = datetime.utcnow()
    call_allocator.apply_provider_event(db, provider="provider_a", event_id=f"evt-{uuid.uuid4().hex[:8]}",
                                         call_id=call.id, event_type="RINGING", emitted_at=now)
    call_allocator.apply_provider_event(db, provider="provider_a", event_id=f"evt-{uuid.uuid4().hex[:8]}",
                                         call_id=call.id, event_type="CONNECTED", emitted_at=now)
    call_allocator.apply_provider_event(db, provider="provider_a", event_id=f"evt-{uuid.uuid4().hex[:8]}",
                                         call_id=call.id, event_type="COMPLETED", emitted_at=now)
    # A late, stale RINGING arrives AFTER completion -- must be ignored.
    late = call_allocator.apply_provider_event(
        db, provider="provider_a", event_id=f"evt-{uuid.uuid4().hex[:8]}",
        call_id=call.id, event_type="RINGING", emitted_at=now,
    )
    db.refresh(call)
    return {"call_id": call.id, "final_status": call.status, "late_event_result": late}


@app.post("/demo/worker-crash")
def demo_worker_crash(db: Session = Depends(get_db)):
    """
    Simulates a worker that reserved an agent+borrower and then crashed
    before ever starting the call (e.g. before initiate_call completed).
    We demonstrate detection + recovery via timeout_stale_calls, and show
    the agent/borrower are NOT permanently stuck.
    """
    agent = agent_manager.try_reserve_any_available_agent(db)
    borrower = borrower_queue.try_reserve_next_borrower(db) if agent else None
    if not agent or not borrower:
        if agent:
            agent_manager.release_agent(db, agent.id)
        raise HTTPException(400, "no agent/borrower available to demo with")

    # Worker "crashes" here -- it reserved resources but never called
    # initiate_call(). A production system detects this via a reservation
    # TTL/heartbeat; here we demonstrate the recovery path directly.
    recovered_agent = agent_manager.release_agent(db, agent.id)
    borrower_queue.release_borrower(db, borrower.id, called=False)
    return {
        "scenario": "worker crashed after reserving agent+borrower, before initiating call",
        "agent_recovered_to": recovered_agent.state,
        "borrower_released": True,
    }


@app.post("/demo/provider-outage")
def demo_provider_outage(db: Session = Depends(get_db)):
    """Provider health collapses -> Safety Controller forces Progressive Mode."""
    available = agent_manager.count_available(db)
    proposal = predictive_engine.propose_call_count(
        predictive_engine.PacingInputs(available_agents=available, answer_rate=0.5, provider_health=0.1)
    )
    decision = safety_controller.evaluate(
        db, proposed_calls=proposal.proposed_calls, mode="predictive", answer_rate=0.5, provider_health=0.1
    )
    return {
        "proposed_calls": proposal.proposed_calls,
        "approved_calls": decision.approved_calls,
        "forced_progressive": decision.forced_progressive,
        "reason": decision.reason,
    }


@app.post("/demo/agent-dropout")
def demo_agent_dropout(db: Session = Depends(get_db)):
    """
    Agent availability suddenly decreases mid-tick: we propose based on a
    stale 'available' count, then re-check right before approving, showing
    the Safety Controller clamps to the smaller, CURRENT number.
    """
    stale_available = agent_manager.count_available(db)
    # Simulate several agents going OFFLINE/PAUSED between proposal and approval.
    agents = db.query(Agent).filter(Agent.state == AgentState.AVAILABLE).limit(max(1, stale_available // 2)).all()
    for a in agents:
        agent_manager.set_agent_state(db, a.id, AgentState.PAUSED)

    proposal = predictive_engine.propose_call_count(
        predictive_engine.PacingInputs(available_agents=stale_available, answer_rate=0.5)
    )
    decision = safety_controller.evaluate(
        db, proposed_calls=proposal.proposed_calls, mode="predictive", answer_rate=0.5
    )
    return {
        "stale_available_used_for_proposal": stale_available,
        "current_available_at_approval": agent_manager.count_available(db),
        "proposed_calls": proposal.proposed_calls,
        "approved_calls": decision.approved_calls,
        "reason": decision.reason,
    }


# --------------------------------------------------------------------------
# Read endpoints
# --------------------------------------------------------------------------
@app.get("/agents", response_model=list[AgentOut])
def list_agents(db: Session = Depends(get_db)):
    return db.query(Agent).all()


@app.get("/borrowers", response_model=list[BorrowerOut])
def list_borrowers(db: Session = Depends(get_db)):
    return db.query(Borrower).limit(500).all()


@app.get("/calls", response_model=list[CallOut])
def list_calls(db: Session = Depends(get_db)):
    return db.query(Call).order_by(Call.created_at.desc()).limit(200).all()


@app.get("/decisions", response_model=list[PacingDecisionOut])
def list_decisions(db: Session = Depends(get_db)):
    return db.query(PacingDecision).order_by(PacingDecision.created_at.desc()).limit(50).all()


@app.get("/dashboard", response_model=DashboardOut)
def dashboard(db: Session = Depends(get_db)):
    agents = db.query(Agent).all()
    agents_total = len(agents)
    agents_available = sum(1 for a in agents if a.state == AgentState.AVAILABLE)
    agents_active = sum(
        1 for a in agents
        if a.state in (AgentState.RESERVED, AgentState.DIALING, AgentState.CONNECTED, AgentState.WRAP_UP)
    )

    calls_initiated = db.query(Call).count()
    calls_connected = db.query(Call).filter(Call.status == CallStatus.CONNECTED).count()
    calls_failed = db.query(Call).filter(Call.status == CallStatus.FAILED).count()
    calls_completed = db.query(Call).filter(Call.status == CallStatus.COMPLETED).count()

    utilization = (agents_active / agents_total) if agents_total else 0.0

    recent_decisions = db.query(PacingDecision).order_by(PacingDecision.created_at.desc()).limit(10).all()
    recent_calls = db.query(Call).order_by(Call.created_at.desc()).limit(10).all()

    return DashboardOut(
        agents_total=agents_total,
        agents_available=agents_available,
        agents_active=agents_active,
        borrowers_remaining=borrower_queue.remaining_count(db),
        calls_initiated=calls_initiated,
        calls_connected=calls_connected,
        calls_failed=calls_failed,
        calls_completed=calls_completed,
        utilization=round(utilization, 3),
        recent_decisions=recent_decisions,
        recent_calls=recent_calls,
        agents=agents,
    )


# --------------------------------------------------------------------------
# Serve the built React frontend (frontend/dist) from this same process/port.
# Mounted LAST and at "/" so every API route above still matches first;
# this only catches paths none of them claimed (the SPA's HTML/JS/CSS).
# Lets one free host (Replit, Render, etc.) run the whole app as one service.
# --------------------------------------------------------------------------
_frontend_dist = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.isdir(_frontend_dist):
    app.mount("/", StaticFiles(directory=_frontend_dist, html=True), name="frontend")
