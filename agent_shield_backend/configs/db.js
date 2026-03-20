const Database = require('better-sqlite3');
const path = require('path');

const db = new Database(path.join(__dirname, 'audit.db'));

db.exec(`
  CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT DEFAULT (datetime('now')),
    method TEXT NOT NULL,
    params TEXT NOT NULL,
    verdict TEXT NOT NULL,
    reason TEXT
  )
`);

module.exports = db;
