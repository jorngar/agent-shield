# Backend API Contract (ai-agent Wrapper)

This document describes the HTTP contract consumed by the Python wrapper in this directory.

## Wrapper call sequence

For a normal session the wrapper interacts with the backend in this order:

1. Optional startup probe: `GET /api/health`
2. For each intercepted event:
   - `POST /api/intercept`
   - `GET /api/intercept/:intercept_id` until the decision is final
3. Final best-effort report: `POST /api/session/result`

Base URL normalization:
- `AGENT_SHIELD_BACKEND_URL` may be configured either as the host root, for example `https://example.execute-api.ap-southeast-1.amazonaws.com`, or with a trailing `/api`
- The client normalizes both forms so routes do not end up double-prefixed

Request timeout behavior:
- Each backend request uses a 5 second client timeout
- All 2xx wrapper routes should return JSON objects; empty `204` responses are not compatible with the current client
- Health failures only produce a warning
- Intercept submission and decision polling are fail-closed
- Session result reporting is best effort

## GET /api/health

Startup connectivity probe.

Example success response:

```json
{
  "status": "ok"
}
```

Wrapper expectations:
- Return a 2xx JSON object, typically `{ "status": "ok" }`
- The wrapper reads `status` when present and falls back to `"ok"` if it is omitted
- Non-2xx responses, invalid JSON, and network failures only produce a startup warning

## POST /api/intercept

Submit one intercepted runtime event for human or policy approval.

Example request:

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

Request field notes:
- `session_id`: UUID generated once when the wrapper starts
- `agent`: currently `"codex"`
- `action_type`: classification assigned by the interceptor
- `content`: either the intercepted command line or a `local_endpoint->remote_endpoint` string for connections
- `risk`: normalized Ollama output plus `latency_ms`

`action_type` values currently emitted by the wrapper:
- `mcp_process_spawn`: command matches MCP detector patterns
- `mcp_shell_target_access`: command references a configured MCP host or port, or a known proxy port
- `child_process_spawn`: non-whitelisted child process spawn in `process-tree` mode
- `shell_process_spawn`: strict-mode shell spawn intercept
- `mcp_connection_attempt`: MCP-related network connection intercept
- `responses_api_connection_attempt`: root Codex HTTPS connection classified as model-provider traffic
- `agent_connection_attempt`: non-whitelisted network connection in `process-tree` or `strict` mode
- `mcp_http_payload`: proxy payload intercept, only when the optional `MCPProxyServer` path is used

Example success response:

```json
{
  "intercept_id": "550e8400-e29b-41d4-a716-446655440001",
  "status": "pending"
}
```

Wrapper expectations:
- A 2xx success response must be JSON and include `intercept_id`
- If `intercept_id` is missing, the wrapper treats the event as denied
- Any non-2xx response is treated as a submission failure and therefore as a deny

## GET /api/intercept/:intercept_id

Poll for a final decision on an intercept.

Example pending response:

```json
{
  "intercept_id": "550e8400-e29b-41d4-a716-446655440001",
  "decision": null,
  "status": "pending"
}
```

Example decided response:

```json
{
  "intercept_id": "550e8400-e29b-41d4-a716-446655440001",
  "decision": "deny",
  "status": "decided"
}
```

Wrapper expectations:
- `decision` must be exactly `"approve"` or `"deny"` to stop polling
- Poll cadence is every `0.5` seconds for up to `60` attempts, or about 30 seconds total
- Non-2xx responses, invalid JSON, and transient network failures are ignored and polling continues
- If polling never returns a final decision, the wrapper defaults to `deny`
- Additional fields such as `reason` are allowed and ignored by the wrapper

## POST /api/session/result

Report the final session outcome after Codex exits or the wrapper fails.

Example request:

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
      "action_type": "mcp_connection_attempt",
      "process_pid": 12345,
      "process_type": "mcp_connection",
      "process_role": "child",
      "connection_scope": "local",
      "detection_reason": "configured_mcp_port"
    }
  ]
}
```

`status` values:
- `success`: Codex exited with code `0` and no denied intercepts occurred
- `blocked`: at least one intercept was denied; this takes precedence even if the wrapper intentionally terminates Codex afterward
- `failed`: wrapper startup failed or Codex exited non-zero

Intercept object notes:
- Every intercept includes core fields such as `intercept_id`, `decision`, `risk_level`, `timestamp`, and `content_preview`
- Process events include fields such as `process_pid`, `process_type`, `event_type=process_spawn`, `action_type`, and `detection_reason`
- Connection events include fields such as `process_role`, `connection_scope`, `event_type=network_connection`, `action_type`, and `detection_reason`
- `content_preview` is truncated by the wrapper to 100 characters before reporting
- `timestamp` is generated with `datetime.utcnow().isoformat()` and therefore has no timezone suffix

Example success response:

```json
{
  "ok": true,
  "session_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

Wrapper expectations:
- Any 2xx JSON response is acceptable
- The wrapper does not retry this call
- A failure here does not change the already computed wrapper exit status

## Failure semantics

The wrapper is intentionally fail-closed for intercept decisions:
- Intercept submission failure, including network error or non-2xx response, results in `deny`
- Missing `intercept_id` from the submit response results in `deny`
- Decision polling timeout results in `deny`

This means backend instability can block agent activity by design.

## Optional or compatibility endpoints

The wrapper does not require these routes, but they are commonly useful for dashboards, admin tooling, or service discovery:
- `GET /api`
- `PUT /api/intercept/:intercept_id/decision`
- `GET /api/session/:session_id`
- `GET /api/intercepts`
- `DELETE /api/intercept/:intercept_id`

Compatibility note:
- The current wrapper contract requires `GET /api/health`, `POST /api/intercept`, `GET /api/intercept/:intercept_id`, and `POST /api/session/result`
