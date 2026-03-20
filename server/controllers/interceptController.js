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
