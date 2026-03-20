# Agent Shield

Agent Shield wraps an AI agent (Codex) and intercepts any MCP-related activity before it can reach unauthorized tools/servers. It performs risk analysis using a local Ollama Qwen model, then relays an allow/deny decision to a backend API.

## Local development (processes)

### Prerequisites
1. Node.js (for the backend)
2. Python 3.9+ (for the wrapper)
3. Ollama running locally with the model pulled
   - `ollama pull qwen3.5:0.8b`

### 1) Start the backend API (Express)
From repo root:
1. `npm install --workspace=server`
2. `npm run dev:server`

The backend defaults to port `3000` (override with `PORT`).

### 2) Start the `ai-agent` wrapper (process-spawn interception)
From repo root:
1. `python3 -m pip install -r ai-agent/requirements.txt`
2. Set environment variables (see `ai-agent/.env-example`)
3. Run:
   - `npm run dev:ai -- --backend http://localhost:3000`

`--backend` must match the Express backend you started.

### 3) Confirm the backend is up
`curl http://localhost:3000/api/health`

## Backend API (local contract)
The wrapper calls these endpoints:
- `POST /api/intercept`
- `GET /api/intercept/:intercept_id`
- `PUT /api/intercept/:intercept_id/decision`
- `POST /api/session/result`

See `ai-agent/BACKEND_API.md`.

## Deploy with CDK (`infra/`)

### What currently deploys
This repo’s `infra/` CDK stack deploys an **EC2 backend** (behind an ALB + API Gateway) and provisions an RDS database.

It does not yet provision Bedrock or Firebase resources in this repo; those will need to be added to the CDK stack when implementing the “Bedrock deeper analysis + Firebase response” path.

### Deploy steps
From repo root:
1. `cd infra`
2. `npm install`
3. `npm run build`
4. `npx cdk synth`
5. `npx cdk deploy`

### Required environment
CDK typically relies on:
- `CDK_DEFAULT_ACCOUNT`
- `CDK_DEFAULT_REGION`

The backend container receives:
- `OLLAMA_HOST` (via `process.env.OLLAMA_HOST` in the CDK stack)

