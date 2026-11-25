import { useEffect, useState, useCallback } from "react";
import { api } from "./services/api";
import StatCard from "./components/StatCard";
import AgentGrid from "./components/AgentGrid";
import DecisionLog from "./components/DecisionLog";
import CallTable from "./components/CallTable";

export default function App() {
  const [dashboard, setDashboard] = useState(null);
  const [mode, setMode] = useState("predictive");
  const [provider, setProvider] = useState("provider_a");
  const [answerRate, setAnswerRate] = useState(0.5);
  const [demoResult, setDemoResult] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const data = await api.dashboard();
      setDashboard(data);
      setError(null);
    } catch (e) {
      setError(String(e));
    }
  }, []);

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, 1500); // poll so async provider events show up live
    return () => clearInterval(interval);
  }, [refresh]);

  const wrap = (fn) => async () => {
    setBusy(true);
    try {
      await fn();
      await refresh();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  };

  const runDemo = (fn, label) => async () => {
    setBusy(true);
    try {
      const result = await fn();
      setDemoResult({ label, result });
      await refresh();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  };

  const util = dashboard ? Math.round(dashboard.utilization * 100) : 0;

  return (
    <div className="app">
      <h1>SmartDialer</h1>
      <p className="subtitle">Progressive + Predictive outbound dialer simulation</p>

      {error && (
        <div className="panel" style={{ borderColor: "var(--red)", color: "var(--red)" }}>
          {error}
        </div>
      )}

      <div className="stat-grid">
        <StatCard value={dashboard?.agents_available ?? "–"} label="Available agents" />
        <StatCard value={dashboard?.agents_active ?? "–"} label="Active agents" />
        <StatCard value={dashboard?.calls_initiated ?? "–"} label="Calls initiated" />
        <StatCard value={dashboard?.calls_connected ?? "–"} label="Connected calls" />
        <StatCard value={dashboard?.calls_failed ?? "–"} label="Failed calls" />
        <StatCard value={dashboard?.calls_completed ?? "–"} label="Completed calls" />
        <StatCard value={dashboard?.borrowers_remaining ?? "–"} label="Borrowers remaining" />
        <StatCard value={`${util}%`} label="Agent utilization" />
      </div>

      <div className="panel">
        <h2>Simulation controls</h2>
        <div className="controls-row">
          <div className="field">
            <label>Dialing mode</label>
            <select value={mode} onChange={(e) => setMode(e.target.value)}>
              <option value="predictive">Predictive</option>
              <option value="progressive">Progressive</option>
            </select>
          </div>
          <div className="field">
            <label>Provider</label>
            <select value={provider} onChange={(e) => setProvider(e.target.value)}>
              <option value="provider_a">Provider A (fast, reliable)</option>
              <option value="provider_b">Provider B (slow, unreliable)</option>
            </select>
          </div>
          <div className="field">
            <label>Answer rate</label>
            <input
              type="number"
              min="0.05"
              max="1"
              step="0.05"
              value={answerRate}
              onChange={(e) => setAnswerRate(parseFloat(e.target.value))}
              style={{ width: 80 }}
            />
          </div>
          <button disabled={busy} onClick={wrap(() => api.tick(mode, provider, answerRate))}>
            Run tick
          </button>
          <button className="secondary" disabled={busy} onClick={wrap(() => api.seed(10, 50))}>
            Seed (10 agents / 50 borrowers)
          </button>
          <button className="secondary" disabled={busy} onClick={wrap(() => api.reset())}>
            Reset
          </button>
        </div>
      </div>

      <div className="panel">
        <h2>Failure handling demos</h2>
        <div className="demo-grid">
          <button className="demo" disabled={busy} onClick={runDemo(api.demoDuplicate, "Duplicate event")}>
            Duplicate event
          </button>
          <button className="demo" disabled={busy} onClick={runDemo(api.demoOutOfOrder, "Out-of-order event")}>
            Out-of-order event
          </button>
          <button className="demo" disabled={busy} onClick={runDemo(api.demoWorkerCrash, "Worker crash")}>
            Worker crash
          </button>
          <button className="demo" disabled={busy} onClick={runDemo(api.demoProviderOutage, "Provider outage")}>
            Provider outage
          </button>
          <button className="demo" disabled={busy} onClick={runDemo(api.demoAgentDropout, "Agent dropout")}>
            Agent dropout
          </button>
        </div>
        {demoResult && (
          <div className="result-box">
            <strong>{demoResult.label}:</strong>
            {"\n"}
            {JSON.stringify(demoResult.result, null, 2)}
          </div>
        )}
      </div>

      <div className="panel">
        <h2>Agents</h2>
        <AgentGrid agents={dashboard?.agents} />
      </div>

      <div className="panel">
        <h2>Recent system decisions</h2>
        <DecisionLog decisions={dashboard?.recent_decisions} />
      </div>

      <div className="panel">
        <h2>Recent calls</h2>
        <CallTable calls={dashboard?.recent_calls} />
      </div>
    </div>
  );
}
