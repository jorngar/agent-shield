const db = require("../configs/db");

exports.getAuditLog = (req, res) => {
  const limit = parseInt(req.query.limit) || 50;
  const rows = db
    .prepare("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?")
    .all(limit);
  res.json(rows);
};
