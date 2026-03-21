const Database = require("better-sqlite3");
const path = require("path");

const dbPath =
  process.env.AGENT_SHIELD_DB_PATH || path.join(__dirname, "audit.db");

const db = new Database(dbPath);

db.exec(`
  CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT DEFAULT (datetime('now')),
    session_id TEXT NOT NULL,
    agent TEXT NOT NULL,
    action_type TEXT NOT NULL,
    content TEXT NOT NULL,
    risk_level TEXT NOT NULL,
    risk_score INTEGER NOT NULL,
    risk_category TEXT NOT NULL,
    risk_summary TEXT NOT NULL,
    risk_flags TEXT,
    latency_ms INTEGER,
    verdict TEXT NOT NULL,
    reason TEXT
  )
`);

db.exec(`
  CREATE TABLE IF NOT EXISTS intercepts (
    intercept_id TEXT PRIMARY KEY,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    session_id TEXT NOT NULL,
    agent TEXT NOT NULL,
    action_type TEXT NOT NULL,
    content TEXT NOT NULL,
    risk_json TEXT NOT NULL,
    decision TEXT NOT NULL,
    status TEXT NOT NULL,
    reason TEXT,
    audit_log_id INTEGER,
    FOREIGN KEY (audit_log_id) REFERENCES audit_log(id)
  )
`);

db.exec(`
  CREATE TABLE IF NOT EXISTS session_results (
    session_id TEXT PRIMARY KEY,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    status TEXT NOT NULL,
    intercepts_json TEXT NOT NULL
  )
`);

db.exec(`
  CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user',
    created_at TEXT DEFAULT (datetime('now'))
  )
`);

module.exports = db;
