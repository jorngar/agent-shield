# ai-agent (Agent Shield wrapper)

`ai-agent` is a Python wrapper around Codex. It launches Codex as a subprocess, watches its process tree and established TCP connections, runs risk analysis through Ollama, and asks a backend approval API whether suspicious activity should continue.

This wrapper is runtime enforcement, not a full sandbox. It can block risky child processes and network connections, but it does not prevent filesystem writes by itself. If you want hard write restrictions, pass Codex a read-only sandbox through `AGENT_SHIELD_CODEX_ARGS`.

## Overview

At a high level the wrapper does this:

1. Loads local environment from `.env` when present.
2. Resolves the Codex command from config, with a runtime fallback to `npx -y @openai/codex` if `codex` is not installed.
3. Refreshes known MCP targets from `codex mcp list --json`, with the same `npx` fallback when needed.
4. Starts Codex with inherited stdio so the TUI behaves normally.
5. Polls the Codex process tree for new descendants and established TCP connections.
6. Classifies suspicious activity, analyzes it with Ollama, and submits an intercept to the backend.
7. Enforces the backend decision:
   - `approve`: allow the process or connection to continue.
   - `deny`: kill the relevant process tree.
8. Reports the final session outcome to the backend.

Important runtime semantics:
- Intercept decisions are fail-closed. Submission failures, missing `intercept_id`, or polling timeout all resolve to `deny`.
- Backend health checks are best effort. Startup continues even if `GET /api/health` fails.
- Final session reporting is best effort. A failed `POST /api/session/result` does not change the already computed wrapper result.
- Backend and Ollama traffic is auto-whitelisted by hostname, localhost alias, and resolved IP address so the wrapper does not self-intercept its own approval and risk-analysis calls.
- Logs go to `.agent-shield.log` by default so Codex TUI output stays clean unless `--verbose` is used.

## Intercept modes

`AGENT_SHIELD_INTERCEPT_MODE` controls how aggressively process and connection events are intercepted.

### `mcp-targets`

Only intercept activity that looks MCP-related:
- A descendant command matches configured MCP patterns: `mcp_process_spawn`
- A command references a configured MCP host or port, or a known proxy port: `mcp_shell_target_access`
- An established connection matches an MCP process, configured MCP host or port, or a known proxy port: `mcp_connection_attempt`

### `process-tree` (default)

Intercept the full Codex process tree except explicitly whitelisted items:
- Any non-whitelisted child process spawn: `child_process_spawn`
- Any non-whitelisted established TCP connection from Codex or a descendant: `agent_connection_attempt`
- Root Codex outbound HTTPS to a non-local host is classified as model-provider traffic: `responses_api_connection_attempt`

### `strict`

Intercept all non-whitelisted descendants more aggressively:
- Any descendant shell process spawn: `shell_process_spawn`
- Any established TCP connection: `agent_connection_attempt`

## Requirements

- Python 3.9+
- Python packages from `requirements.txt`
- POSIX-style monitoring tools available on the host: `pgrep`, `ps`, `lsof`, `kill`
- A backend service that implements the contract in `BACKEND_API.md`
- Ollama running with an available model
- Either a `codex` binary on `PATH` or `npx`

Default toolchain values:
- Ollama host: `http://localhost:11434`
- Ollama model: `qwen3.5:0.8b`
- Backend URL: `http://localhost:3000`

## Local setup

1. Install Python dependencies:

   ```bash
   python3 -m pip install -r requirements.txt
   ```

2. Copy the example environment and adjust it for your machine:

   ```bash
   cp .env-example .env
   ```

3. Start Ollama and make sure the configured model is available.

4. Start the approval backend.

Environment loading behavior:
- `config.py` loads `.env` from the module directory first, then from the current working directory if it is different.
- Existing process environment variables always win over `.env` values.
- Inside the same `.env` file, later assignments override earlier ones.
- `.env-example` defaults Codex to `-s read-only`, so the wrapper starts with filesystem writes sandboxed unless you change it.

For AWS or API Gateway deployments:
- Set `AGENT_SHIELD_BACKEND_URL` to the API host root such as `https://...execute-api...amazonaws.com`
- A value ending in `/api` also works; the client normalizes both forms

## Run

Direct examples:

```bash
python3 cli.py
python3 cli.py --backend http://localhost:3000
python3 cli.py --backend http://localhost:3000 -- --help
AGENT_SHIELD_BACKEND_URL=https://n73h8lxc41.execute-api.ap-southeast-1.amazonaws.com python3 cli.py
```

`npm` script wrappers:

```bash
npm run dev -- --help
npm test
```

`package.json` does not add extra runtime behavior. The `npm` scripts are thin wrappers around the same Python entrypoints.

## CLI

```bash
python3 cli.py [--backend URL] [--verbose] [codex_args ...]
```

Arguments:
- `--backend`: backend API base URL, overriding `AGENT_SHIELD_BACKEND_URL`
- `--verbose` / `-v`: also mirror interceptor logs to stderr
- `codex_args`: forwarded to the resolved Codex command

Startup output:
- Prints the backend URL and active intercept mode
- Probes `GET /api/health` and prints either `Backend health: ok` or a warning

Exit codes:
- `0`: session completed with status `success` or `blocked`
- `1`: startup failure, runtime error, or user interrupt

## Configuration

### Core environment variables

- `AGENT_SHIELD_OLLAMA_HOST`: Ollama base URL, default `http://localhost:11434`
- `AGENT_SHIELD_OLLAMA_MODEL`: Ollama model name, default `qwen3.5:0.8b`
- `AGENT_SHIELD_BACKEND_URL`: backend base URL, default `http://localhost:3000`
- `AGENT_SHIELD_CODEX_COMMAND`: shell-split command used to start Codex, default `codex`
- `AGENT_SHIELD_CODEX_ARGS`: default shell-split arguments passed to Codex

Codex argument compatibility:
- Legacy `--dangerously-skip-possible-errors` is automatically rewritten to `--dangerously-bypass-approvals-and-sandbox`
- If `AGENT_SHIELD_CODEX_COMMAND` resolves to `codex` and no local binary exists, runtime falls back to `npx -y @openai/codex`

### Interception tuning

- `AGENT_SHIELD_INTERCEPT_MODE`: `mcp-targets`, `process-tree`, or `strict`
- `AGENT_SHIELD_PROCESS_SCAN_INTERVAL_SEC`: descendant scan cadence in seconds, default `0.1`, minimum `0.05`
- `AGENT_SHIELD_RESPONSES_API_HOSTS`: comma-separated hostnames treated as model-provider API destinations, default `api.openai.com`

### Logging and allowlists

- `AGENT_SHIELD_LOG_FILE`: log path, default `.agent-shield.log`
- `AGENT_SHIELD_WHITELIST_HOSTS`: comma-separated host allowlist, case-insensitive
- `AGENT_SHIELD_WHITELIST_PORTS`: comma-separated numeric port allowlist
- `AGENT_SHIELD_WHITELIST_COMMAND_PATTERNS`: comma-separated case-insensitive command substrings

Whitelist behavior:
- Backend and Ollama endpoints are auto-whitelisted, including localhost aliases such as `localhost`, `127.0.0.1`, and `::1`
- For non-local backend or Ollama hosts, resolved IP addresses are also auto-whitelisted so established TLS sockets still bypass interception after DNS resolution
- Connection allowlisting checks both local and remote endpoints on each established socket, which prevents self-intercepts on the server side of backend or Ollama listener sockets
- Explicit whitelist environment variables extend the auto-whitelist
- Whitelisted commands skip process-spawn interception, and whitelisted endpoints skip connection interception

Monitoring scope:
- The wrapper watches descendant process spawns and established TCP connections only
- Connection inspection is based on `lsof`; there is no UDP or packet-level capture
- `MCPProxyServer` exists as an optional helper for HTTP payload interception, but `cli.py` does not start it by default

## Project layout

- `cli.py`: command-line entrypoint and startup diagnostics
- `config.py`: environment loading and configuration normalization
- `.env-example`: example local wrapper configuration
- `mcp_interceptor.py`: main process-tree monitor, connection classifier, and enforcement logic
- `mcp_detector.py`: MCP-related string and command detection helpers
- `risk_engine.py`: Ollama request and risk result normalization
- `api_client.py`: backend health, intercept, polling, and session-result client
- `tests/`: unit tests for config, backend client, risk parsing, and interceptor helpers
- `BACKEND_API.md`: backend contract consumed by this wrapper

## Testing

Run the unit test suite with either command:

```bash
npm test
python3 -m unittest discover -s tests -p 'test_*.py'
```

The current tests are mock-heavy unit tests. They validate configuration parsing, request shaping, intercept classification, and result handling, but they do not spin up a live Codex process, Ollama instance, or backend service.

## Backend API

See `BACKEND_API.md` for the exact request and response contract used by the wrapper.
