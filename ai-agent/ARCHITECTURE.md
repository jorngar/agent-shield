# Architecture

This document describes the current runtime architecture of `ai-agent` as implemented in this repository. It is the design view of the Python wrapper that launches Codex, observes runtime behavior, evaluates risk, and enforces approval decisions.

## Purpose

`ai-agent` is a runtime enforcement wrapper around Codex. Its job is to:

- start Codex as a subprocess without breaking the interactive TUI experience
- watch the Codex process tree for suspicious child processes and TCP connections
- classify and score those events with a local risk engine backed by Ollama
- optionally escalate uncertain events to a backend approval service
- enforce the final decision by allowing the activity, killing a child process tree, or soft-blocking/auditing a root-process connection
- report the final session outcome to the backend

This is not a full sandbox. The wrapper observes and reacts to behavior after launch. Filesystem restrictions only exist if Codex itself is started with a sandbox such as `-s read-only`.

## System Context

```text
User Terminal
    |
    v
cli.py
    |
    v
MCPInterceptor --------------------------------------+
    |                                                 |
    | launches                                        | submits/polls/report
    v                                                 v
Codex subprocess tree                            Backend API
    |                                                 ^
    | process + network inspection                    |
    v                                                 |
OS tools: pgrep, ps, lsof, kill                       |
    |                                                 |
    +------------------ risk context -----------------+
    |
    v
risk_engine.py -> Ollama HTTP API
```

## High-Level Flow

### 1. Startup

`cli.py` reads CLI arguments, prints startup diagnostics, constructs `MCPInterceptor`, and performs a best-effort backend health check.

`config.py` is imported early and normalizes runtime configuration from:

- process environment
- `.env` next to the module
- `.env` in the current working directory

Existing environment variables win over `.env`, and later assignments in the same `.env` file override earlier ones.

### 2. Codex Launch

`MCPInterceptor.run()`:

- refreshes known MCP targets from `codex mcp list --json`
- resolves the Codex command from config, with `npx -y @openai/codex` fallback when `codex` is unavailable
- launches Codex with inherited stdio so the terminal UI behaves normally
- snapshots already-open remote connections on the root process so inherited sockets are not misclassified as new agent behavior

### 3. Monitoring

The interceptor starts a background monitor thread that repeatedly:

- walks the Codex descendant tree with `pgrep`
- reads full command lines with `ps`
- inspects listening and established TCP sockets with `lsof`
- detects newly seen child PIDs
- detects newly seen established TCP connections
- schedules async intercept handlers onto the main event loop

### 4. Decision Pipeline

Every intercepted event flows through the same broad pipeline:

1. Classify the event into an `action_type`.
2. Build risk context from command, process, and connection metadata.
3. Call `risk_engine.analyze_risk()` against Ollama.
4. Normalize the risk result.
5. Run local triage:
   - low-risk approve can be allowed locally
   - high-risk deny can be blocked locally
   - the review band is escalated to the backend
6. If escalated, submit the intercept and poll for a final decision.
7. Enforce the final decision.
8. Append an intercept record to in-memory session history.

### 5. Session Finalization

When Codex exits, or the wrapper terminates it, `report_session()` computes final session status:

- `success`: Codex exited cleanly with no denied intercepts
- `blocked`: at least one intercept was denied, or the shield terminated the root process
- `failed`: startup/runtime failure or a non-zero Codex exit without a blocking decision

The wrapper then sends a best-effort `POST /api/session/result`.

## Runtime Components

### `cli.py`

Thin entrypoint responsible for:

- CLI argument parsing
- startup banner and diagnostics
- backend health probe
- invoking the interceptor and printing the final summary

### `config.py`

Central configuration layer responsible for:

- `.env` loading
- backend URL normalization
- Codex command and argument normalization
- intercept mode selection
- concurrency, risk-threshold, whitelist, and degraded-mode settings

This module is intentionally simple and mostly computes constants at import time.

### `mcp_interceptor.py`

This is the orchestration core. It owns:

- Codex process lifecycle
- descendant and connection monitoring
- event classification
- local state for seen processes/connections and intercept history
- risk-analysis invocation
- local triage and backend escalation
- decision enforcement
- session reporting

Key internal state includes:

- `session_id`
- `intercepts`
- `_seen_pids`
- `_seen_connections`
- `_seen_connection_signatures`
- `_baseline_remote_endpoints`
- `_mcp_target_hosts` / `_mcp_target_ports`
- `_whitelist_hosts` / `_whitelist_ports` / `_whitelist_endpoints`
- `_backend_degraded_until`

### `mcp_detector.py`

Pattern-based helper for MCP-related detection. It recognizes:

- MCP package names
- well-known server names
- MCP protocol references

It is deliberately lightweight and string-based; it does not parse shell syntax or protocol payloads deeply.

### `risk_engine.py`

Encapsulates the Ollama integration. It:

- builds a structured system prompt and user prompt
- requests JSON output from the configured local model
- extracts and parses JSON from imperfect model responses
- normalizes the result into a stable contract
- falls back to a review-oriented medium-risk result when Ollama is unavailable or malformed

### `api_client.py`

Async HTTP client for the approval backend. It is responsible for:

- `GET /api/health`
- `POST /api/intercept`
- `GET /api/intercept/:id`
- `POST /api/session/result`

It normalizes backend base URLs so both `https://host` and `https://host/api` work.

### `MCPProxyServer` in `mcp_interceptor.py`

Optional HTTP proxy path that can submit raw MCP payloads into the same risk and decision pipeline. It exists as an extension point but is not started by `cli.py` by default.

## Interception Model

The wrapper intercepts two main event classes:

- process spawns
- established TCP connections

### Intercept Modes

`AGENT_SHIELD_INTERCEPT_MODE` controls how broad interception is:

- `mcp-targets`
  - intercepts explicit MCP-like process spawns
  - intercepts commands referencing configured MCP hosts or ports
  - intercepts connections to configured MCP targets
- `process-tree`
  - default mode
  - intercepts non-whitelisted child process spawns
  - intercepts non-whitelisted network activity across the Codex process tree
- `strict`
  - intercepts descendant shell activity more aggressively
  - intercepts all non-whitelisted established TCP connections

Destructive file-operation commands are intercepted in all modes, including `mcp-targets`.

### Action Types

Important emitted `action_type` values include:

- `mcp_process_spawn`
- `mcp_shell_target_access`
- `destructive_file_operation`
- `child_process_spawn`
- `shell_process_spawn`
- `mcp_connection_attempt`
- `responses_api_connection_attempt`
- `agent_connection_attempt`
- `mcp_http_payload`

## Connection Classification

Connection handling is more opinionated than process handling because the wrapper needs to avoid self-intercepts and routine noise.

Before a connection becomes an intercept candidate, the interceptor filters out:

- inherited baseline sockets that existed immediately after launch
- explicit whitelist hosts, ports, and endpoint pairs
- backend and Ollama traffic, including resolved IPs
- local loopback IPC that does not look MCP-related
- internal private/link-local network traffic that does not look MCP-related
- Codex root-process traffic that is identified as its own Responses API path

Remaining connections are classified into MCP, Responses API, or generic agent connection categories depending on process role, remote endpoint, and intercept mode.

## Decision Architecture

The decision path is intentionally split into local and cloud stages.

### Local Stage

The local stage uses the normalized risk result:

- approve locally when the model says `approve`, the level is `low`, and the score is at or below `LOCAL_APPROVE_MAX_SCORE`
- deny locally when the model says `deny`, the level is `high` or `critical`, and the score is at or above `LOCAL_DENY_MIN_SCORE`
- send everything else to cloud review

This keeps obviously safe and obviously dangerous cases off the critical path of backend latency.

### Cloud Stage

For review-band events, the wrapper:

1. submits the event to the backend
2. expects an `intercept_id`
3. polls until `decision` becomes `approve` or `deny`

The backend path is treated as degraded when submit fails or polling times out. During a degraded window, review-band events skip cloud escalation and use `AGENT_SHIELD_CLOUD_REVIEW_FAILURE_MODE` instead. The default implementation is a graceful fallback to `approve`.

## Enforcement Semantics

The enforcement model is targeted rather than global.

### Hard Block

For denied child-process spawns and denied child-process connections, the wrapper kills the target PID and its descendants:

- `SIGTERM` first
- short grace period
- `SIGKILL` for survivors

If the denied PID is not the root Codex PID, the root process is explicitly excluded from the kill set.

### Soft Block

If the backend or local policy denies a root-process network connection, the event is recorded as denied but the wrapper does not kill Codex. This preserves the session while still auditing the decision.

### Session Outcome Rules

- any denied intercept makes the session `blocked`
- a shield-caused root termination also reports `blocked`
- a plain non-zero exit without a deny reports `failed`

## Concurrency Model

The code uses a mixed async/threaded design:

- the main control path runs on `asyncio`
- process and socket polling runs in a background thread
- blocking shell commands and network inspection are moved through `asyncio.to_thread()` when used inside async handlers
- cross-thread work submission uses `asyncio.run_coroutine_threadsafe()`
- intercept handling is bounded by an async semaphore via `AGENT_SHIELD_MAX_CONCURRENT_INTERCEPTS`

This architecture keeps the UI responsive while allowing blocking OS inspection tools to be used safely.

## Trust Boundaries

The main trust boundaries are:

- Codex and its descendants: treated as untrusted runtime activity
- local OS inspection tools: trusted observability layer
- Ollama: trusted enough to score risk, but not trusted for final correctness without normalization and policy thresholds
- backend approval API: trusted for review decisions when reachable

The wrapper auto-whitelists its own backend and Ollama endpoints to avoid recursively intercepting its control traffic.

## Observability

Operational visibility comes from:

- `.agent-shield.log` file logging
- optional stderr mirroring via `--verbose`
- in-memory intercept history included in final session reporting

Logging is deliberately separated from Codex stdio so the interactive TUI remains usable.

## Limitations

Current design limitations:

- no filesystem, syscall, or packet-level sandboxing
- TCP inspection only; no UDP coverage
- polling-based observation rather than event-driven tracing
- MCP detection is heuristic and string-based
- process identity checks are best-effort and command-line based
- optional HTTP proxy interception exists but is not in the default launch path
- tests are primarily unit tests with mocks, not end-to-end integration tests

## Repository Map

- `cli.py`: entrypoint
- `config.py`: configuration and env loading
- `mcp_interceptor.py`: orchestration, monitoring, enforcement
- `mcp_detector.py`: MCP detection helpers
- `risk_engine.py`: Ollama integration and risk normalization
- `api_client.py`: backend HTTP client
- `tests/`: unit coverage for config, client, risk parsing, and interceptor behavior
- `BACKEND_API.md`: backend contract document

## Design Summary

The system is a small control loop around Codex:

- observe process and connection activity
- classify events into intercepts
- score risk locally
- escalate only the uncertain middle
- enforce decisions as close as possible to the offending process
- preserve a clean user terminal and report the final session state

That makes `ai-agent` a runtime policy wrapper, not a container or kernel sandbox.
