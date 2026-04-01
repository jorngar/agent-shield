# Agent Shield

Agent Shield is a runtime security wrapper for AI coding agents. It launches your agent as a subprocess and intercepts MCP-related activity, child process spawns, and network connections — analyzing each with a local LLM before allowing or blocking.

**Supported agents:** Codex, Kilo, Claude Code, OpenClaw, Hermes Agent, Gemini CLI

## Quick Start

### Prerequisites
1. Node.js (for the backend)
2. Python 3.9+ (for the local wrapper)
3. Ollama running locally with the risk model pulled
   - `ollama pull qwen3.5:0.8b`

### Option A: Local-Only Mode (no backend required)

The fastest way to get started — everything runs on your machine:

```bash
pip install -r ai-agent/requirements.txt

# Local-only with live dashboard
python3 ai-agent/cli.py --local-only --dashboard

# Local-only without dashboard
python3 ai-agent/cli.py --local-only

# Pick an agent
python3 ai-agent/cli.py --local-only --agent kilo --dashboard
```

The dashboard opens at `http://localhost:3200` showing real-time intercepts, risk levels, and decisions.

**What local-only mode does:**
- No backend API calls — fully offline
- Ollama performs risk analysis (with policy-based fallback if Ollama is unavailable)
- Low/medium/high risk actions handled by local triage
- Medium-risk actions use `AGENT_SHIELD_CLOUD_REVIEW_FAILURE_MODE` (default: approve)
- Dashboard provides visual monitoring of all intercepts

### Option B: With Backend API (human-in-the-loop approval)

For production setups with the approval dashboard:

**1) Start the backend API:**
```bash
npm install --workspace=server
npm run dev:server
```

**2) Start the wrapper:**
```bash
cp ai-agent/.env-example .env
python3 ai-agent/cli.py --backend http://localhost:3000
```

**3) Confirm the backend is up:**
```bash
curl http://localhost:3000/api/health
```

### CLI Reference

```bash
# Basic usage
python3 ai-agent/cli.py [OPTIONS]

# Options:
  --agent NAME          Which agent to wrap (codex, kilo, claude-code, openclaw, hermes-agent, geminicli)
  --backend URL         Backend API URL (default: http://localhost:3000)
  --local-only          Skip backend — run entirely local with risk engine + triage
  --dashboard           Start local dashboard (implies --local-only unless --backend given)
  --dashboard-port N    Dashboard port (default: 3200)
  -v, --verbose         Print interceptor logs to stderr

# Forward args to the agent after --
python3 ai-agent/cli.py --agent codex -- --help
```

### Environment Variables

```bash
# Set default agent
export AGENT_SHIELD_AGENT=codex

# Run local-only by default
export AGENT_SHIELD_LOCAL_ONLY=true
export AGENT_SHIELD_LOCAL_DASHBOARD_PORT=3200

# Local LLM config
export AGENT_SHIELD_OLLAMA_HOST=http://localhost:11434
export AGENT_SHIELD_OLLAMA_MODEL=qwen3.5:0.8b
export AGENT_SHIELD_OLLAMA_TIMEOUT=60

# What to do when cloud review is unavailable (local-only uses this for medium-risk)
export AGENT_SHIELD_CLOUD_REVIEW_FAILURE_MODE=approve  # or "deny"
```

## Supported Agents

| Agent | CLI name | Default command | API hosts |
|-------|----------|-----------------|-----------|
| Codex | `--agent codex` | `codex` / `npx @openai/codex` | `api.openai.com` |
| Kilo | `--agent kilo` | `kilo` | configurable via `AGENT_SHIELD_KILO_API_HOSTS` |
| Claude Code | `--agent claude-code` | `claude` | `api.anthropic.com` |
| OpenClaw | `--agent openclaw` | `openclaw` | configurable via `AGENT_SHIELD_OPENCLAW_API_HOSTS` |
| Hermes | `--agent hermes-agent` | `hermes` | configurable via `AGENT_SHIELD_HERMES_API_HOSTS` |
| Gemini CLI | `--agent geminicli` | `gemini` | `generativelanguage.googleapis.com` |

Each agent adapter handles:
- **Command resolution** — finding the agent binary, falling back to npx
- **Process identity** — recognizing the agent's own runtime processes
- **MCP discovery** — reading MCP server configs from the agent's config files
- **API classification** — detecting connections to the agent's model API
- **Flag sanitization** — stripping config flags that bias the risk engine

### Adding a New Agent

Create a new file in `ai-agent/agents/`, implement `AgentAdapter`, and register it:

```python
# agents/my_agent.py
from agents.base import AgentAdapter
from agents import register_adapter

@register_adapter("my_agent")
class MyAgentAdapter(AgentAdapter):
    @property
    def name(self) -> str:
        return "my-agent"
    # ... implement remaining methods
```

Then import it in `agents/__init__.py`. The CLI will automatically pick it up.

## Local Dashboard

The `--dashboard` flag starts a built-in web dashboard for monitoring intercepts in real time. No external dependencies — uses only Python's standard library.

```bash
python3 ai-agent/cli.py --local-only --dashboard
# Open http://localhost:3200

# Custom port
python3 ai-agent/cli.py --local-only --dashboard --dashboard-port 8080
```

**Dashboard features:**
- Session ID, agent name, running status
- Live intercept count, blocked/approved counters
- Table view: time, action type, process role, risk level, decision, content preview
- Auto-refreshes every 2 seconds
- JSON API at `/api/state` and `/api/intercepts`

## Ollama Health Check

On startup, Agent Shield validates the Ollama connection:
- Checks if the Ollama daemon is reachable
- Verifies the configured model is pulled
- Pre-warms the model to avoid cold-start latency on the first intercept

If Ollama is unavailable, the shield continues with policy-based fallbacks (no LLM analysis). Clear error messages guide you to fix the issue:

```
[AgentShield] Ollama preflight FAILED: Cannot connect to Ollama at http://localhost:11434.
              Is the Ollama daemon running?  Start it with: ollama serve
[AgentShield] Shield will continue with policy-based fallbacks only (no LLM risk analysis).
```

## Configuration

All config is via environment variables prefixed with `AGENT_SHIELD_`. See `ai-agent/.env-example` for the full list.

Key settings:
| Variable | Default | Description |
|----------|---------|-------------|
| `AGENT_SHIELD_AGENT` | `codex` | Default agent to wrap |
| `AGENT_SHIELD_LOCAL_ONLY` | `false` | Skip backend, run local-only |
| `AGENT_SHIELD_LOCAL_DASHBOARD_PORT` | `3200` | Dashboard port |
| `AGENT_SHIELD_INTERCEPT_MODE` | `process-tree` | `mcp-targets`, `process-tree`, or `strict` |
| `AGENT_SHIELD_BACKEND_URL` | `http://localhost:3000` | Approval API endpoint |
| `AGENT_SHIELD_OLLAMA_HOST` | `http://localhost:11434` | Local risk model endpoint |
| `AGENT_SHIELD_OLLAMA_MODEL` | `qwen3.5:0.8b` | Ollama model to use |
| `AGENT_SHIELD_OLLAMA_TIMEOUT` | `60` | Request timeout (seconds) |
| `AGENT_SHIELD_MAX_CONCURRENT_INTERCEPTS` | `4` | Max simultaneous risk analyses |
| `AGENT_SHIELD_CLOUD_REVIEW_FAILURE_MODE` | `approve` | Fallback decision when cloud unavailable |

## Backend API

The wrapper calls these endpoints (skipped in `--local-only` mode):
- `POST /api/intercept` — submit an action for approval
- `GET /api/intercept/:intercept_id` — poll for decision
- `PUT /api/intercept/:intercept_id/decision` — manual override
- `POST /api/session/result` — report session outcome

See `ai-agent/BACKEND_API.md` for the full contract.

## Deploy with CDK (`infra/`)

### What currently deploys
This repo's `infra/` CDK stack deploys an **EC2 backend** (behind an ALB + API Gateway) and provisions an RDS database.

### Deploy steps
From repo root:
1. `cd infra`
2. `npm install`
3. `npm run build`
4. `npx cdk synth`
5. `npx cdk deploy`

### Required environment
- `CDK_DEFAULT_ACCOUNT`
- `CDK_DEFAULT_REGION`

## Testing

```bash
# Python wrapper tests (109 tests)
cd ai-agent && python3 -m pytest tests/ -v

# Backend tests (10 tests)
npm test --workspace=server
```

**Test coverage:**
| File | Tests | What's covered |
|------|-------|----------------|
| `test_mcp_interceptor.py` | 39 | Classification, triage, backend fallback, dedup |
| `test_integration.py` | 34 | Adapter unit tests, local-only mode, dashboard, full pipeline, process scanning |
| `test_vuln_scan.py` | 17 | Version detection, LLM response parsing, scan orchestration |
| `test_risk_engine.py` | 8 | Risk parsing, normalization, analyze with retry/timeout |
| `test_api_client.py` | 5 | URL normalize, health check, intercept submit/poll |
| `test_config.py` | 3 | Env loading, codex args |

## Vulnerability Scanning

On startup, Agent Shield scans the target agent's dependencies for known CVEs and supply-chain compromises using the local LLM:

```
[AgentShield] Agent: codex
[AgentShield] Ollama ready (latency=234ms, model_warmed=True)
[VulnScan] OK: codex v0.2.1 — no known vulnerabilities (1205ms)
```

If vulnerabilities are detected:

```
[VulnScan] WARNING: my-agent v1.0 — HIGH vulnerabilities detected (1523ms)
  - CVE-2026-1234: RCE in dependency
  - CVE-2026-5678: Supply-chain compromise
  Recommendation: Update to latest version immediately
```

The scan runs once before the agent launches and never blocks startup. Disable with:
```bash
export AGENT_SHIELD_VULN_SCAN=false
```

## Project Structure

```
agent-shield/
├── ai-agent/                    # Python wrapper
│   ├── agents/                  # Agent adapters (plugin pattern)
│   │   ├── __init__.py          # Registry
│   │   ├── base.py              # AgentAdapter ABC
│   │   ├── codex.py             # OpenAI Codex adapter
│   │   ├── claude_code.py       # Anthropic Claude Code adapter
│   │   ├── kilo.py              # Kilo adapter
│   │   ├── gemini_cli.py        # Google Gemini CLI adapter
│   │   ├── openclaw.py          # OpenClaw adapter
│   │   └── hermes_agent.py      # Hermes adapter
│   ├── cli.py                   # CLI entry point
│   ├── config.py                # Environment-based config
│   ├── mcp_interceptor.py       # Core interception engine
│   ├── mcp_detector.py          # MCP pattern detection
│   ├── risk_engine.py           # Ollama risk analysis + health check
│   ├── api_client.py            # Backend HTTP client
│   ├── local_dashboard.py       # Built-in local dashboard
│   └── tests/                   # Test suite
├── server/                      # Express.js backend API
├── client/                      # Frontend (admin dashboard)
└── infra/                       # AWS CDK deployment
```
