const db = require("../configs/db");
const evaluate = require("../helpers/evaluate");

exports.intercept = (req, res) => {
  const { session_id, agent, action_type, content, risk } = req.body;

  if (!session_id || !agent || !action_type || !content || !risk) {
    return res
      .status(400)
      .json({ error: "Missing required fields: session_id, agent, action_type, content, risk" });
  }

  const { verdict, reason } = evaluate(risk);

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

  res.json({ id: result.lastInsertRowid, session_id, verdict, reason });
};

exports.getStatus = (req, res) => {
  const { id } = req.params;

  const row = db
    .prepare("SELECT id, timestamp, session_id, agent, action_type, verdict, reason FROM audit_log WHERE id = ?")
    .get(id);

  if (!row) {
    return res.status(404).json({ error: "Not found" });
  }

  res.json(row);
};
