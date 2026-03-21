# Backend API Contract (ai-agent Wrapper)

This document describes the API contract used by the Python wrapper in this directory.

## Endpoints used by wrapper

The wrapper directly calls:
- `GET /api/health`
- `POST /api/intercept`
- `GET /api/intercept/:intercept_id`
- `POST /api/session/result`

`/api/session/result` should exist, but wrapper execution does not fail if this call returns an error.
`/api/health` is used as a startup diagnostic; an unhealthy or unreachable response only produces a warning.

Base URL note:
- The wrapper accepts `AGENT_SHIELD_BACKEND_URL` with or without a trailing `/api`.
- Requests are normalized so the client still calls the routes documented here without double-prefixing `/api`.

## GET /api/health

Startup connectivity probe.

### Success response example

```json
{
  "status": "ok"
}
```

Rules expected by wrapper:
- Any 2xx JSON response with `status` is treated as healthy.
- Non-2xx responses, invalid JSON, and network failures are reported as warnings only; startup continues.

## POST /api/intercept

Submit one intercept event for approval.

### Request

```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "agent": "codex",
  "action_type": "mcp_connection_attempt",
  "content": "127.0.0.1:54000->127.0.0.1:3001",
  "risk": {
    "risk_level": "high",
    "risk_score": 85,
    "category": "mcp_unauthorized",
    "summary": "Suspicious MCP-related connection attempt detected.",
    "recommended_action": "deny",
    "flags": ["mcp", "network"],
    "latency_ms": 420
  }
}
```

### `action_type` values used by wrapper

- `mcp_process_spawn`: command matches MCP detector patterns
- `mcp_shell_target_access`: command references configured MCP host/port or known MCP proxy port
- `child_process_spawn`: non-whitelisted child process spawn in `process-tree` mode
- `shell_process_spawn`: strict-mode shell spawn intercept
- `mcp_connection_attempt`: MCP-related network connection intercept
- `responses_api_connection_attempt`: root Codex HTTPS connection classified as model-provider API traffic
- `agent_connection_attempt`: non-whitelisted network connection in `process-tree` or `strict` mode
- `mcp_http_payload`: proxy payload intercept (only if `MCPProxyServer` path is used)

### Success response (2xx)

```json
{
  "intercept_id": "550e8400-e29b-41d4-a716-446655440001",
  "status": "pending"
}
```

Rules expected by wrapper:
- `intercept_id` must be present to start decision polling.
- If response is non-2xx, wrapper treats submission as error and defaults to `deny`.
- If response is 2xx but `intercept_id` is missing, wrapper also defaults to `deny`.

---

## GET /api/intercept/:intercept_id

Poll for a decision on an intercept.

### Pending response example

```json
{
  "intercept_id": "550e8400-e29b-41d4-a716-446655440001",
  "decision": null,
  "status": "pending"
}
```

### Decided response example

```json
{
  "intercept_id": "550e8400-e29b-41d4-a716-446655440001",
  "decision": "deny",
  "status": "decided"
}
```

Rules expected by wrapper:
- `decision` must be either `"approve"` or `"deny"` to stop polling.
- Poll cadence: every `0.5s`, up to `60` attempts (~30 seconds).
- Non-2xx responses and invalid JSON are treated as transient polling failures (continue polling).
- If polling never yields `approve`/`deny`, wrapper defaults to `deny`.

---

## POST /api/session/result

Report final wrapper session result.

### Request

```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "blocked",
  "intercepts": [
    {
      "intercept_id": "550e8400-e29b-41d4-a716-446655440001",
      "decision": "deny",
      "risk_level": "high",
      "timestamp": "2026-03-20T10:30:00.000000",
      "event_type": "network_connection",
      "content_preview": "127.0.0.1:54000->127.0.0.1:3001",
      "detection_reason": "configured_mcp_port"
    }
  ]
}
```

### `status` values

- `success`: Codex exited with code `0` and no denied intercepts
- `blocked`: at least one deny decision occurred
- `failed`: startup error or non-zero Codex exit

### Success response (2xx)

```json
{
  "ok": true,
  "session_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

Notes:
- Intercept objects can include additional fields such as `event_type`, `action_type`, `process_pid`, `process_type`, `connection_scope`, and `detection_reason`.
- Wrapper does not retry this endpoint and does not change already-computed session status if this call fails.

---

## Wrapper failure semantics

The client behaves fail-closed for intercept decisions:
- Intercept submission failure (network/HTTP/non-2xx) => deny.
- Missing `intercept_id` from submit response => deny.
- Decision polling timeout or unresolved polling failures => deny.

This means backend instability can block MCP-related operations by design.

---

## Optional endpoints (Dashboard/Admin)

The wrapper does not call these directly, but they are commonly useful:

- `PUT /api/intercept/:intercept_id/decision`
- `GET /api/session/:session_id`
- `GET /api/intercepts`
- `GET /api/health`
- `DELETE /api/intercept/:intercept_id`
