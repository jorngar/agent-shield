const db = require("../configs/db");
const evaluate = require("../helpers/evaluate");
const { randomUUID } = require("node:crypto");

exports.intercept = (req, res) => {
  const { session_id, agent, action_type, content, risk } = req.body;

  if (!session_id || !agent || !action_type || !content || !risk) {
    return res
      .status(400)
      .json({ error: "Missing required fields: session_id, agent, action_type, content, risk" });
  }

  const { verdict, reason } = evaluate(risk);
  const interceptId = randomUUID();
  const status = verdict === "pending" ? "pending" : "decided";

  const stmt = db.prepare(
    `INSERT INTO audit_log
      (session_id, agent, action_type, content, risk_level, risk_score, risk_category, risk_summary, risk_flags, latency_ms, verdict, reason)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
  );

  const result = stmt.run(
    session_id,
    agent,
    action_type,
    content,
    risk.risk_level,
    risk.risk_score,
    risk.category,
    risk.summary,
    JSON.stringify(risk.flags),
    risk.latency_ms,
    verdict,
    reason,
  );

  db.prepare(
    `INSERT INTO intercepts
      (intercept_id, session_id, agent, action_type, content, risk_json, decision, status, reason, audit_log_id)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
  ).run(
    interceptId,
    session_id,
    agent,
    action_type,
    content,
    JSON.stringify(risk),
    verdict,
    status,
    reason,
    result.lastInsertRowid,
  );

  res.json({ intercept_id: interceptId, status });
};

exports.getStatus = (req, res) => {
  const { id } = req.params;

  const row = db
    .prepare(
      "SELECT intercept_id, created_at, session_id, agent, action_type, decision, status, reason FROM intercepts WHERE intercept_id = ?",
    )
    .get(id);

  if (!row) {
    return res.status(404).json({ error: "Not found" });
  }

  const response = {
    intercept_id: row.intercept_id,
    status: row.status,
    reason: row.reason,
  };

  if (row.decision === "approve" || row.decision === "deny") {
    response.decision = row.decision;
  }

  res.json(response);
};

exports.resolveDecision = (req, res) => {
  const { id } = req.params;
  const { decision, reason } = req.body || {};

  if (!decision || !["approve", "deny"].includes(decision)) {
    return res.status(400).json({ error: "Decision must be 'approve' or 'deny'" });
  }

  const existing = db.prepare("SELECT audit_log_id FROM intercepts WHERE intercept_id = ?").get(id);
  if (!existing) {
    return res.status(404).json({ error: "Intercept not found" });
  }

  const resolvedReason = reason || `Manual decision: ${decision}`;

  db.prepare(
    "UPDATE intercepts SET decision = ?, status = 'decided', reason = ?, updated_at = datetime('now') WHERE intercept_id = ?",
  ).run(decision, resolvedReason, id);

  if (existing.audit_log_id) {
    db.prepare("UPDATE audit_log SET verdict = ?, reason = ? WHERE id = ?").run(
      decision,
      resolvedReason,
      existing.audit_log_id,
    );
  }

  return res.json({
    intercept_id: id,
    status: "decided",
    decision,
    reason: resolvedReason,
  });
};
