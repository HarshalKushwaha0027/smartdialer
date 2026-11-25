const STATUS_COLOR = {
  INITIATED: { bg: "#1d2d4a", fg: "#5b8def" },
  RINGING: { bg: "#3a3414", fg: "#e3b341" },
  CONNECTED: { bg: "#143a2e", fg: "#2ee6a6" },
  FAILED: { bg: "#3a1420", fg: "#e5597b" },
  COMPLETED: { bg: "#15321f", fg: "#35c48c" },
};

export default function CallTable({ calls }) {
  if (!calls?.length) {
    return <p style={{ color: "var(--text-dim)", fontSize: 13 }}>No calls yet.</p>;
  }
  return (
    <div>
      {calls.map((c) => {
        const col = STATUS_COLOR[c.status] || STATUS_COLOR.INITIATED;
        return (
          <div className="call-row" key={c.id}>
            <div>
              {c.id} · {c.provider} · {c.mode}
            </div>
            <span className="badge" style={{ background: col.bg, color: col.fg }}>
              {c.status}
            </span>
          </div>
        );
      })}
    </div>
  );
}
