# ai-agent (Agent Shield wrapper)

Python wrapper that launches Codex and intercepts suspicious process/network activity before it is allowed to continue.

## What it does

1. Starts Codex as a subprocess with inherited stdio (TTY-friendly behavior).
2. Loads configured MCP targets from `codex mcp list --json` (or `npx -y @openai/codex ...` fallback).
3. Monitors Codex child processes plus established TCP connections from Codex itself and its descendants.
4. Runs risk analysis via local Ollama.
5. Sends intercept payloads to backend approval API.
6. Enforces decision:
   - `approve`: allow process/connection.
   - `deny`: kill the process tree.
7. Reports final session status to backend.

Fail-closed behavior:
- If intercept submission fails (network/HTTP/non-2xx), decision defaults to `deny`.
- If polling never returns `approve` or `deny` (~30s default), decision defaults to `deny`.
- Logs are written to `.agent-shield.log` by default so Codex TUI output is not polluted.

Scope:
- This wrapper does not hard-sandbox filesystem writes.
- It intercepts and blocks based on runtime process/network activity.
- For hard write prevention, run Codex with a read-only sandbox via `AGENT_SHIELD_CODEX_ARGS`.

## Intercept modes

`AGENT_SHIELD_INTERCEPT_MODE` controls how aggressively process/connection events are intercepted.

### `mcp-targets`

Intercept when a descendant process/connection looks MCP-related:
- Command matches MCP patterns (`action_type=mcp_process_spawn`).
- Command references configured MCP host/port or known MCP proxy ports (`action_type=mcp_shell_target_access`).
- Established connection matches MCP process/targets/ports (`action_type=mcp_connection_attempt`).

### `process-tree` (default)

Intercept all non-whitelisted child processes and all non-whitelisted connections from the Codex process tree:
- Any child process spawn (`action_type=child_process_spawn`).
- Any non-whitelisted established connection from Codex or a child (`action_type=agent_connection_attempt`).
- Codex root outbound HTTPS is classified as Responses API traffic (`action_type=responses_api_connection_attempt`) unless whitelisted.

### `strict`

Intercept all non-whitelisted descendants:
- Any shell process spawn (`action_type=shell_process_spawn`).
- Any established connection (`action_type=agent_connection_attempt`).

## Requirements

- Python 3.9+
- Dependencies from `requirements.txt`
- System tools used by monitoring: `pgrep`, `ps`, `lsof`, `kill`
- Backend service implementing the contract in `BACKEND_API.md`
- Ollama running with an available model (default `qwen3.5:0.8b`)

Codex command resolution:
- Uses `AGENT_SHIELD_CODEX_COMMAND` if set.
- Default command is `codex`.
- If `codex` is unavailable, it falls back to `npx -y @openai/codex`.

## Local setup

1. Install dependencies:
   - `python3 -m pip install -r requirements.txt`
2. Configure environment (optional but recommended):
   - `cp .env-example .env`
   - `set -a; source .env; set +a`
   - `python3 cli.py` and `npm run start` also auto-load `ai-agent/.env` if present.
3. Start backend service (default expected URL: `http://localhost:3000`).
   - For AWS/API Gateway deployment, set `AGENT_SHIELD_BACKEND_URL` to your API endpoint instead of using `localhost`.

## Run

- Direct:
  - `python3 cli.py --backend http://localhost:3000`
  - `python3 cli.py --backend http://localhost:3000 -- --help`
  - `AGENT_SHIELD_BACKEND_URL=https://n73h8lxc41.execute-api.ap-southeast-1.amazonaws.com python3 cli.py`
- Via npm scripts:
  - `npm run dev -- --help`

Run tests:
- `npm test`

## CLI

`python3 cli.py [--backend URL] [--verbose] [codex_args ...]`

- `--backend`: backend API base URL (default: `AGENT_SHIELD_BACKEND_URL` or `http://localhost:3000`)
- `--verbose` / `-v`: mirror interceptor logs to stderr (logs are always written to `AGENT_SHIELD_LOG_FILE`)
- `codex_args`: forwarded to Codex invocation

Startup diagnostics:
- The wrapper prints the active intercept mode.
- The wrapper probes `GET /api/health` and warns if the configured backend is unreachable.

Exit behavior:
- Exit `0`: session `success` or `blocked`
- Exit `1`: startup/runtime failure or interrupt

## Environment variables

- `AGENT_SHIELD_OLLAMA_HOST` (default `http://localhost:11434`)
- `AGENT_SHIELD_OLLAMA_MODEL` (default `qwen3.5:0.8b`)
- `AGENT_SHIELD_BACKEND_URL` (default `http://localhost:3000`)
- `AGENT_SHIELD_CODEX_COMMAND` (default `codex`, shell-split)
- `AGENT_SHIELD_CODEX_ARGS` (default empty, shell-split)
- `AGENT_SHIELD_INTERCEPT_MODE` (`mcp-targets`, `process-tree`, or `strict`, default `process-tree`)
- `AGENT_SHIELD_PROCESS_SCAN_INTERVAL_SEC` (default `0.1`, minimum `0.05`)
- `AGENT_SHIELD_LOG_FILE` (default `.agent-shield.log`)
- `AGENT_SHIELD_RESPONSES_API_HOSTS` (comma-separated hostnames, default `api.openai.com`)
- `AGENT_SHIELD_WHITELIST_HOSTS` (comma-separated hosts, case-insensitive)
- `AGENT_SHIELD_WHITELIST_PORTS` (comma-separated ports)
- `AGENT_SHIELD_WHITELIST_COMMAND_PATTERNS` (comma-separated command substrings, case-insensitive)

Whitelist behavior:
- Backend URL and Ollama URL are auto-whitelisted (including localhost aliases) to prevent self-block loops.
- For AWS deployment, the wrapper only needs `AgentShieldStack.ApiEndpoint`; `ClusterName`, `DatabaseEndpoint`, and `LoadBalancerDns` are backend/ops values, not wrapper config.
- Explicit whitelist env vars extend the auto-whitelist.

## Backend API

See `BACKEND_API.md` for request/response details.
