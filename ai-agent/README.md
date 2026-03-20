# ai-agent (Agent Shield wrapper)

This wrapper launches Codex as a subprocess and intercepts MCP-related activity using process-spawn inspection.

When an MCP-related process is detected, it:
1. collects basic network signals for the process (listening/established connections),
2. runs risk analysis via the local Ollama Qwen model (master risk prompt),
3. submits the risk payload to the backend for approval/deny,
4. if denied, kills the process tree.

## Run (local)

From repo root:
1. Install wrapper deps: `python3 -m pip install -r ai-agent/requirements.txt`
2. Start backend: `npm run dev:server`
3. Start wrapper:
   - `npm run dev:ai -- --backend http://localhost:3000`

## Environment variables

Set the variables in your shell using `ai-agent/.env-example` as a template.

Key variables:
- `AGENT_SHIELD_OLLAMA_HOST` (default `http://localhost:11434`)
- `AGENT_SHIELD_OLLAMA_MODEL` (default `qwen3.5:0.8b`)
- `AGENT_SHIELD_BACKEND_URL` (default `http://localhost:3000`)
- `AGENT_SHIELD_CODEX_COMMAND` (default `codex`)
- `AGENT_SHIELD_CODEX_ARGS` (default empty)

