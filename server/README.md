# agent-shield-server (Express backend)

This service provides the backend API used by the `ai-agent` wrapper for intercept approvals and the Tinyfish research workflow.

## Local run

From repo root:
1. `cd server`
2. `npm install`
3. `cp .env-example .env`
4. `npm run dev`

## Configuration

- `PORT` (optional, default `3000`)
- `TINYFISH_API_KEY` (required for Tinyfish research route)
- `TINYFISH_RESEARCH_URL` (optional, default `https://www.google.com/`)
- `TINYFISH_BROWSER_PROFILE` (`lite` or `stealth`, default `lite`)
- `TINYFISH_RESEARCH_GOAL` (optional override for the default vulnerability research prompt)
- `VULNERABILITY_REFRESH_LIMIT` (optional, default `100`)
- `VULNERABILITY_INTEL_TABLE` (optional, default `agent_vulnerability_intel`)
- `DATABASE_HOST`, `DATABASE_PORT`, `DATABASE_NAME`, `DATABASE_USERNAME`, `DATABASE_PASSWORD` (required for stored vulnerability intel in Postgres)
- `DATABASE_SSL` (optional, set to `require` if your Postgres endpoint requires TLS)
- `AGENT_SHIELD_DB_PATH` (optional SQLite path, useful for tests)

Example:
`PORT=4000 npm run dev`

## Routes

Quick index:
- `GET /`
- `GET /api`

The wrapper expects:
- `POST /api/intercept`
- `GET /api/intercept/:intercept_id`
- `PUT /api/intercept/:intercept_id/decision`
- `POST /api/session/result`

Health check:
- `GET /api/health`

Tinyfish research:
- `GET /api/research/agent-vulnerabilities`
- `POST /api/research/agent-vulnerabilities` (compatibility alias for cached reads)
- `POST /api/research/agent-vulnerabilities/refresh` (manual refresh)

Example request:

```json
{
  "url": "https://www.google.com/",
  "goal": "search for the up to date top 100 ai agent vulnerabilities, exploits and possible harmful executions across the web for me, rank them with criticity and show me potential fixes for them and examples of how can they look",
  "limit": 100,
  "table_name": "agent_vulnerability_intel"
}
```

Runtime behavior:
- API reads serve cached findings from Postgres.
- Tinyfish refresh is intended to run out-of-band on a schedule, not per request.
- A manual refresh endpoint exists for ops/admin use.
