const db = require("../configs/db");
const VERDICTS = require("../helpers/verdicts");

exports.getAuditLog = (req, res) => {
  const limit = parseInt(req.query.limit) || 50;
  const rows = db
    .prepare("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?")
    .all(limit);
  res.json(rows);
};

exports.resolveDecision = (req, res) => {
  const { id } = req.params;
  const { verdict } = req.body;

  if (!verdict || ![VERDICTS.APPROVE, VERDICTS.DENY].includes(verdict)) {
    return res.status(400).json({ error: "Verdict must be 'approve' or 'deny'" });
  }

  const row = db.prepare("SELECT * FROM audit_log WHERE id = ?").get(id);

  if (!row) {
    return res.status(404).json({ error: "Audit entry not found" });
  }

  if (row.verdict !== VERDICTS.PENDING) {
    return res.status(400).json({ error: `Cannot update a non-pending entry (current: ${row.verdict})` });
  }

  db.prepare("UPDATE audit_log SET verdict = ?, reason = ? WHERE id = ?")
    .run(verdict, `Human decision: ${verdict}`, id);

  res.json({ id: Number(id), verdict, reason: `Human decision: ${verdict}` });
};
