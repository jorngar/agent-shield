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
- `AGENT_SHIELD_DB_PATH` (optional SQLite path, useful for tests)

Example:
`PORT=4000 npm run dev`

## Routes

The wrapper expects:
- `POST /api/intercept`
- `GET /api/intercept/:intercept_id`
- `PUT /api/intercept/:intercept_id/decision`
- `POST /api/session/result`

Health check:
- `GET /api/health`

Tinyfish research:
- `POST /api/research/agent-vulnerabilities`

Example request:

```json
{
  "url": "https://www.google.com/",
  "goal": "search for the up to date top 100 ai agent vulnerabilities, exploits and possible harmful executions across the web for me, rank them with criticity and show me potential fixes for them and examples of how can they look",
  "limit": 100,
  "table_name": "agent_vulnerability_intel"
}
```

The research route returns:
- normalized findings
- a PostgreSQL `CREATE TABLE IF NOT EXISTS`
- a parameterized `INSERT ... ON CONFLICT DO UPDATE`
- the matching `insert_params` array
