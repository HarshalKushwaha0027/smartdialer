const COLORS = {
  OFFLINE: "#3a4258",
  AVAILABLE: "#15321f",
  RESERVED: "#3a3414",
  DIALING: "#1d2d4a",
  CONNECTED: "#143a2e",
  WRAP_UP: "#3a2a14",
  PAUSED: "#3a1420",
};

const TEXT_COLORS = {
  OFFLINE: "#8d97b0",
  AVAILABLE: "#35c48c",
  RESERVED: "#e3b341",
  DIALING: "#5b8def",
  CONNECTED: "#2ee6a6",
  WRAP_UP: "#e3b341",
  PAUSED: "#e5597b",
};

export default function AgentGrid({ agents }) {
  if (!agents?.length) {
    return <p style={{ color: "var(--text-dim)", fontSize: 13 }}>No agents yet — seed the simulation.</p>;
  }
  return (
    <div className="agent-grid">
      {agents.map((a) => (
        <div
          key={a.id}
          className="agent-chip"
          style={{ background: COLORS[a.state], color: TEXT_COLORS[a.state] }}
          title={a.id}
        >
          <div>{a.name}</div>
          <div style={{ fontWeight: 700, marginTop: 2 }}>{a.state}</div>
        </div>
      ))}
    </div>
  );
}
