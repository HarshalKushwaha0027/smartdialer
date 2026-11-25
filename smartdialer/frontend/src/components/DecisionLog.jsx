function badge(decision) {
  if (decision.approved_calls < decision.proposed_calls) {
    return <span className="badge" style={{ background: "#3a3414", color: "#e3b341" }}>Reduced</span>;
  }
  return <span className="badge" style={{ background: "#15321f", color: "#35c48c" }}>Safe</span>;
}

export default function DecisionLog({ decisions }) {
  if (!decisions?.length) {
    return <p style={{ color: "var(--text-dim)", fontSize: 13 }}>No decisions yet — run a simulation tick.</p>;
  }
  return (
    <div>
      {decisions.map((d) => (
        <div className="decision-row" key={d.id}>
          <div>
            <div>
              <strong>{d.mode}</strong> — proposed {d.proposed_calls}, approved {d.approved_calls}
            </div>
            <div style={{ color: "var(--text-dim)", fontSize: 12, marginTop: 2 }}>{d.reason}</div>
          </div>
          <div>{badge(d)}</div>
        </div>
      ))}
    </div>
  );
}
