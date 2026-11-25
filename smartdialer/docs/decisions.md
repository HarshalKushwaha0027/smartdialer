# Architecture decisions & trade-offs

## Database: SQLite for the prototype, PostgreSQL for production

The code uses SQLAlchemy exclusively (no raw dialect-specific SQL), and the
atomic-reservation pattern (`UPDATE ... WHERE state = 'AVAILABLE'`) behaves
identically on both engines. Switching is a one-line change:

```
SMARTDIALER_DATABASE_URL=postgresql://user:pass@host/db
```

PostgreSQL would be the production choice because it gives real
multi-process concurrent write throughput and row-level locking guarantees
under far higher load than SQLite's single-writer model — but for a
single-process prototype demonstrating correctness, SQLite removes all
setup friction and the correctness properties (atomicity of the conditional
UPDATE) are identical.

## No Redis, no Kafka, no ML framework

- **Redis** — would help if we needed a distributed lock or cache shared
  across multiple backend processes. At prototype scale, the database
  transaction *is* the lock. Adding Redis here would be complexity without
  a corresponding correctness or performance benefit.
- **Kafka** — the assignment's "events" are a handful of provider callbacks
  per call, not a high-throughput stream requiring partitioning, replay, or
  multiple independent consumers. A table with a uniqueness constraint
  solves the actual problem (idempotency) directly.
- **TensorFlow / PyTorch** — the assignment explicitly accepts a
  statistical/rule-based pacing model. `floor(available_agents /
  answer_rate)` is transparent, auditable, and trivially testable — exactly
  the properties you want in the component that decides how many customers
  to simultaneously call. An ML model here would trade explainability for
  no real accuracy gain at this stage, and would need its own training,
  monitoring and drift-detection machinery to be trustworthy in a dialer
  safety path.

## Safety Controller: strict one-agent-per-call, no controlled over-dialing

**What we built:** `safe_capacity = available_agents - active_agents`, and
`approved_calls = min(proposed_calls, safe_capacity)`. This means the system
never has more in-flight call attempts than agents available to take them —
a verifiable invariant (`backend/tests/test_safety.py`).

**What a production system would add:** real predictive dialers
deliberately over-dial — starting slightly more calls than confirmed
available agents, betting that not all of them will be answered — to push
utilization above what strict 1:1 reservation allows. This is safe only
when bounded by a *mathematically defined answer-risk budget* (e.g., "dial
at most `available_agents * (1 + risk_budget)`, where `risk_budget` is
derived from the live abandonment-rate target") and only when a
deterministic hard cap still sits on top of it. We did not implement
over-dialing because:

1. It adds a second layer of probabilistic risk management that the
   one-hour prototype doesn't have time to test properly, and
2. The assignment's highest-weighted component (Safety & correctness, 15%,
   plus "never allows more connected calls than available agents" called
   out explicitly) rewards a simple, provably-correct guard far more than a
   flashier but harder-to-verify one.

The hook is there: `safety_controller.evaluate()` is the single chokepoint
any future over-dialing budget would plug into, without touching the
pacing engine or the allocator.

## Idempotency key design

We key on `(provider, event_id)` rather than just `event_id`, because two
independent mock providers could coincidentally mint the same id; scoping by
provider avoids a false-positive "duplicate" across providers while still
catching true duplicates from the same provider.

## Borrower "already called" semantics

A borrower is marked `already_called = True` on **both** `COMPLETED` and
`FAILED` terminal states — one dial attempt, successful or not, is enough to
retire them from the queue for this exercise. (A production system would
likely distinguish "no answer — retry later" from "answered and refused" —
out of scope here, called out as a known simplification.)

## What's explicitly out of scope / simplified

- No real telecom integration (per the assignment).
- No authentication/authorization on the API (single-tenant prototype).
- No persistence of simulation "runs" as separate named sessions — one
  dataset at a time, reset via `/simulation/reset`.
- No WebSocket push for the dashboard; it polls `/dashboard` every 1.5s,
  which is sufficient to visualize the compressed-timescale simulation and
  avoids the added complexity of a socket layer for a demo.
