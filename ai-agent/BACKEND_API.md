# Backend API Contract

## POST /api/intercept

Submit an MCP server attempt for approval.

**Request:**
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "agent": "codex",
  "action_type": "mcp_server",
  "content": "npx @modelcontextprotocol/server-filesystem /data",
  "risk": {
    "risk_level": "high",
    "risk_score": 85,
    "category": "mcp_unauthorized",
    "summary": "Codex is attempting to connect to unauthorized MCP filesystem server",
    "recommended_action": "deny",
    "flags": ["filesystem_mcp", "unauthorized_access", "data_exposure_risk"]
  }
}
```

**Response:**
```json
{
  "intercept_id": "550e8400-e29b-41d4-a716-446655440001",
  "status": "pending",
  "timestamp": "2024-01-15T10:30:00.000Z"
}
```

---

## GET /api/intercept/:intercept_id

Poll for decision on an intercept.

**Response (pending):**
```json
{
  "intercept_id": "550e8400-e29b-41d4-a716-446655440001",
  "decision": null,
  "status": "pending"
}
```

**Response (decided):**
```json
{
  "intercept_id": "550e8400-e29b-41d4-a716-446655440001",
  "decision": "deny",
  "status": "decided",
  "risk": {
    "risk_level": "high",
    "risk_score": 85,
    "category": "mcp_unauthorized"
  }
}
```

---

## PUT /api/intercept/:intercept_id/decision

Manually set a decision (for admin/dashboard).

**Request:**
```json
{
  "decision": "deny"
}
```

**Response:**
```json
{
  "intercept_id": "550e8400-e29b-41d4-a716-446655440001",
  "decision": "deny",
  "status": "decided"
}
```

---

## POST /api/session/result

Report final session result.

**Request:**
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "blocked",
  "intercepts": [
    {
      "intercept_id": "550e8400-e29b-41d4-a716-446655440001",
      "decision": "deny",
      "risk_level": "high"
    }
  ]
}
```

**Response:**
```json
{
  "ok": true,
  "session_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

---

## GET /api/session/:session_id

Get all intercepts for a session.

**Response:**
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "intercepts": [...],
  "total": 3
}
```

---

## GET /api/intercepts

List all intercepts (with optional filtering).

**Query Params:**
- `status` (optional): "pending" | "decided"
- `limit` (optional): number (default 50)

**Response:**
```json
{
  "intercepts": [...],
  "total": 42
}
```

---

## GET /api/health

Health check.

**Response:**
```json
{
  "status": "ok",
  "timestamp": "2024-01-15T10:30:00.000Z",
  "intercepts": 42,
  "sessions": 10
}
```

---

## DELETE /api/intercept/:intercept_id

Delete an intercept.

**Response:**
```json
{
  "ok": true
}
```
