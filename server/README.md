# agent-shield-server (Express backend)

This service provides the local backend API used by the `ai-agent` wrapper for intercept approvals.

## Local run

From repo root:
1. `npm install --workspace=server`
2. `npm run dev:server`

## Configuration

- `PORT` (optional, default `3000`)

Example:
`PORT=4000 npm run dev:server`

## Routes

The wrapper expects:
- `POST /api/intercept`
- `GET /api/intercept/:intercept_id`
- `PUT /api/intercept/:intercept_id/decision`
- `POST /api/session/result`

Health check:
- `GET /api/health`

