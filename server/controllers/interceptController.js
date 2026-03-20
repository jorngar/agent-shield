const db = require("../configs/db");
const evaluate = require("../helpers/evaluate");

exports.intercept = (req, res) => {
  const { tool_name, tool_args, summary } = req.body;

  if (!tool_name || !tool_args || !summary) {
    return res
      .status(400)
      .json({ error: "Missing tool_name, tool_args, or summary" });
  }

  const { verdict, reason } = evaluate({ tool_name, tool_args, summary });

  const stmt = db.prepare(
    "INSERT INTO audit_log (tool_name, tool_args, summary, verdict, reason) VALUES (?, ?, ?, ?, ?)",
  );
  const result = stmt.run(
    tool_name,
    JSON.stringify(tool_args),
    summary,
    verdict,
    reason,
  );

  res.json({ id: result.lastInsertRowid, verdict, reason });
};

exports.getStatus = (req, res) => {
  const { id } = req.params;

  const row = db.prepare("SELECT id, timestamp, tool_name, verdict, reason FROM audit_log WHERE id = ?").get(id);

  if (!row) {
    return res.status(404).json({ error: "Not found" });
  }

  res.json(row);
};
