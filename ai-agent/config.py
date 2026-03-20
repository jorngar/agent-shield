import os
import shlex

OLLAMA_HOST = os.getenv("AGENT_SHIELD_OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("AGENT_SHIELD_OLLAMA_MODEL", "qwen3.5:0.8b")
BACKEND_URL = os.getenv("AGENT_SHIELD_BACKEND_URL", "http://localhost:3000")

# Use local `codex` binary by default and fall back in runtime if unavailable.
CODEX_COMMAND = shlex.split(os.getenv("AGENT_SHIELD_CODEX_COMMAND", "codex"))
CODEX_ARGS = shlex.split(os.getenv("AGENT_SHIELD_CODEX_ARGS", ""))

MCP_PATTERNS = [
    r"@modelcontextprotocol",
    r"server-filesystem",
    r"brave-search",
    r"github-tools",
    r"slack-mcp",
    r"sqlite",
    r"aws-kb-retrieval",
    r"everything",
    r"puppeteer",
    r"mcp-server",
    r"--mcp",
    r"--dangerously-auto-approve-mcp-servers",
]

# Used by `MCPDetector.is_allowed_command()`.
# Note: current MCP detection primarily uses `detect()/scan_content()`;
# this list mainly exists to prevent import/runtime errors.
ALLOWED_COMMANDS = []

BLOCKED_MCP_SERVERS = [
    "filesystem",
    "brave-search",
    "github-tools",
    "slack",
    "sqlite",
    "aws-kb",
    "everything",
    "puppeteer",
]

INTERCEPTABLE_PORTS = [3100, 3101, 3102, 3103, 3104, 3105]
