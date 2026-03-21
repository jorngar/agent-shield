const db = require("../configs/db");

exports.reportSessionResult = (req, res) => {
  const { session_id, status, intercepts } = req.body || {};

  if (!session_id || !status || !Array.isArray(intercepts)) {
    return res.status(400).json({
      error: "Missing required fields: session_id, status, intercepts",
    });
  }

  db.prepare(
    `INSERT INTO session_results (session_id, status, intercepts_json)
     VALUES (?, ?, ?)
     ON CONFLICT(session_id) DO UPDATE SET
       status = excluded.status,
       intercepts_json = excluded.intercepts_json,
       updated_at = datetime('now')`,
  ).run(session_id, status, JSON.stringify(intercepts));

  return res.json({ ok: true, session_id });
};
