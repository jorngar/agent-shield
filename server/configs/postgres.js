const { Pool } = require("pg");

let pool;

function isPostgresConfigured() {
  return Boolean(
    process.env.DATABASE_HOST &&
      process.env.DATABASE_PORT &&
      process.env.DATABASE_NAME &&
      process.env.DATABASE_USERNAME &&
      process.env.DATABASE_PASSWORD,
  );
}

function getPool() {
  if (!isPostgresConfigured()) {
    const error = new Error("Postgres vulnerability store is not configured");
    error.code = "POSTGRES_NOT_CONFIGURED";
    throw error;
  }

  if (!pool) {
    pool = new Pool({
      host: process.env.DATABASE_HOST,
      port: Number.parseInt(process.env.DATABASE_PORT, 10),
      database: process.env.DATABASE_NAME,
      user: process.env.DATABASE_USERNAME,
      password: process.env.DATABASE_PASSWORD,
      ssl:
        String(process.env.DATABASE_SSL || "").toLowerCase() === "require"
          ? { rejectUnauthorized: false }
          : false,
    });
  }

  return pool;
}

async function query(text, params = []) {
  const client = getPool();
  return client.query(text, params);
}

async function closePostgresPool() {
  if (pool) {
    await pool.end();
    pool = undefined;
  }
}

module.exports = {
  closePostgresPool,
  getPool,
  isPostgresConfigured,
  query,
};
