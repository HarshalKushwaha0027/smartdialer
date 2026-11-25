# SmartDialer

A progressive + predictive outbound call dialer prototype, built around one
core idea: **predictive dialing is just "run the safe progressive primitive
N times," where N comes from a Safety Controller that a Pacing Engine never
gets to bypass.**

See [`docs/architecture.md`](docs/architecture.md) for diagrams and state
machines, and [`docs/decisions.md`](docs/decisions.md) for trade-offs and
what was deliberately left out.

## Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11+, FastAPI |
| Database | SQLite (dev) / PostgreSQL (production-ready via `DATABASE_URL`) |
| ORM / validation | SQLAlchemy 2.x, Pydantic 2.x |
| Frontend | React + Vite |
| Testing | Pytest |

## Project layout

```
smartdialer/
├── backend/
│   ├── main.py              # FastAPI app, routes, simulation tick
│   ├── models.py             # ORM models + state machines
│   ├── schemas.py             # Pydantic request/response models
│   ├── database.py            # engine/session setup
│   ├── services/
│   │   ├── agent_manager.py        # atomic agent reservation + state machine
│   │   ├── borrower_queue.py       # atomic borrower reservation
│   │   ├── progressive_dialer.py   # one agent, one call
│   │   ├── predictive_engine.py    # proposes a call count (never dials)
│   │   ├── safety_controller.py    # the only component allowed to approve dials
│   │   └── call_allocator.py       # initiates calls, applies events idempotently
│   ├── providers/
│   │   ├── provider_a.py    # fast, reliable mock provider
│   │   └── provider_b.py    # slow, duplicate/out-of-order mock provider
│   └── tests/
│       ├── test_allocation.py   # concurrency: two workers, one agent
│       ├── test_safety.py       # pacing math + capacity guard + outage/dropout
│       └── test_events.py       # idempotency + out-of-order + worker crash
├── frontend/
│   └── src/ (App.jsx, components/, services/api.js)
└── docs/
    ├── architecture.md
    └── decisions.md
```

## Fastest path: run it online (no local setup)

The whole app — frontend and backend — runs as a single FastAPI process
(FastAPI serves the built React app itself, see `backend/main.py`'s static
mount). That means it can be deployed to a free, browser-only host with no
local Python/Node install needed:

1. Go to **replit.com** and sign in (free).
2. **Create Repl → Import from Upload** (or drag-and-drop) → upload this
   whole `smartdialer` folder (or re-zip it first).
3. Replit detects `.replit` automatically and runs `bash start.sh`, which
   installs dependencies, builds the frontend once, and starts the server.
4. Click **Run**. After the first build (~30–60s), Replit shows a webview
   with a public URL — that's your live SmartDialer dashboard.

The same `start.sh` / single-process setup also works unmodified on Render,
Railway, Fly.io, or any host that runs one command and exposes `$PORT`.

## Setup

### Backend

```bash
cd smartdialer
pip install -r backend/requirements.txt
uvicorn backend.main:app --reload --port 8000
```

The API is now at `http://localhost:8000` (interactive docs at `/docs`).
A SQLite file `smartdialer.db` is created automatically on first run. To use
PostgreSQL instead:

```bash
export SMARTDIALER_DATABASE_URL="postgresql://user:pass@localhost/smartdialer"
```

### Frontend

```bash
cd smartdialer/frontend
npm install
npm run dev
```

Open `http://localhost:5173`. The dev server proxies `/api/*` to the backend
on port 8000 (see `vite.config.js`), so no CORS configuration is needed in
dev.

### Tests

```bash
cd smartdialer
pytest backend/tests -v
```

18 tests covering atomic concurrency, idempotency, out-of-order events,
worker-crash recovery, pacing math, and the safety capacity guard.

## Using the dashboard

1. Click **Seed** to create 10 agents and 50 borrowers.
2. Pick a mode (Progressive / Predictive), a provider, and an answer rate,
   then click **Run tick**. Each tick:
   - Progressive mode starts exactly one call.
   - Predictive mode asks the Pacing Engine to propose a count, has the
     Safety Controller approve/reduce it, then starts that many calls by
     calling the progressive primitive repeatedly.
3. Watch agents flip through their state machine and calls resolve
   (RINGING → CONNECTED/FAILED → COMPLETED) as mock provider events arrive
   asynchronously in the background.
4. Use the **Failure handling demos** panel to trigger each of the five
   required scenarios on demand and see the raw result:
   - Duplicate event
   - Out-of-order event
   - Worker crash (reserved resources recovered, not leaked)
   - Provider outage (forces Progressive Mode)
   - Agent dropout mid-tick (Safety Controller re-checks before approving)

## API reference (selected)

| Method & path | Purpose |
|---|---|
| `POST /seed` | Create agents + borrowers |
| `POST /simulation/tick` | Run one dial cycle (`mode`, `provider`, `answer_rate`) |
| `POST /simulation/reset` | Wipe all data |
| `GET /dashboard` | Aggregated state for the UI |
| `GET /agents` `/borrowers` `/calls` `/decisions` | Raw listings |
| `POST /demo/duplicate-event` | Fires the same event id twice |
| `POST /demo/out-of-order-event` | Fires a stale event after completion |
| `POST /demo/worker-crash` | Simulates crash-after-reservation + recovery |
| `POST /demo/provider-outage` | Forces Progressive Mode via low provider health |
| `POST /demo/agent-dropout` | Shows re-check of availability before approval |

## Known limitations

See "What's explicitly out of scope / simplified" in
[`docs/decisions.md`](docs/decisions.md) — no auth, no controlled
over-dialing budget, no WebSocket push (dashboard polls every 1.5s).
