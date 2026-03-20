const db = require("../configs/db");
const evaluate = require("../helpers/evaluate");

exports.intercept = (req, res) => {
  const { method, params } = req.body;

  if (!method || !params) {
    return res.status(400).json({ error: "Missing method or params" });
  }

  const { verdict, reason } = evaluate({ method, params });

  const stmt = db.prepare(
    "INSERT INTO audit_log (method, params, verdict, reason) VALUES (?, ?, ?, ?)",
  );
  const result = stmt.run(method, JSON.stringify(params), verdict, reason);

  res.json({ id: result.lastInsertRowid, verdict, reason });
};
