import os
import shlex


def _normalize_url(value: str, default: str) -> str:
    normalized = (value or "").strip() or default
    return normalized.rstrip("/")


OLLAMA_HOST = _normalize_url(
    os.getenv("AGENT_SHIELD_OLLAMA_HOST", "http://localhost:11434"),
    "http://localhost:11434",
)
OLLAMA_MODEL = os.getenv("AGENT_SHIELD_OLLAMA_MODEL", "qwen3.5:0.8b")
BACKEND_URL = _normalize_url(
    os.getenv("AGENT_SHIELD_BACKEND_URL", "http://localhost:3000"),
    "http://localhost:3000",
)

# Use local `codex` binary by default and fall back in runtime if unavailable.
CODEX_COMMAND = shlex.split(os.getenv("AGENT_SHIELD_CODEX_COMMAND", "codex"))
CODEX_ARGS = shlex.split(os.getenv("AGENT_SHIELD_CODEX_ARGS", ""))

INTERCEPT_MODE = os.getenv("AGENT_SHIELD_INTERCEPT_MODE", "mcp-targets").strip().lower()
if INTERCEPT_MODE not in {"mcp-targets", "strict"}:
    INTERCEPT_MODE = "mcp-targets"

try:
    PROCESS_SCAN_INTERVAL_SEC = float(
        os.getenv("AGENT_SHIELD_PROCESS_SCAN_INTERVAL_SEC", "0.2")
    )
except ValueError:
    PROCESS_SCAN_INTERVAL_SEC = 0.2
PROCESS_SCAN_INTERVAL_SEC = max(0.05, PROCESS_SCAN_INTERVAL_SEC)

LOG_FILE = os.getenv("AGENT_SHIELD_LOG_FILE", ".agent-shield.log").strip()


def _parse_csv_env(value: str) -> list[str]:
    parts = []
    for token in (value or "").split(","):
        cleaned = token.strip()
        if cleaned:
            parts.append(cleaned)
    return parts


WHITELIST_HOSTS = [host.lower() for host in _parse_csv_env(os.getenv("AGENT_SHIELD_WHITELIST_HOSTS", ""))]

WHITELIST_PORTS = []
for token in _parse_csv_env(os.getenv("AGENT_SHIELD_WHITELIST_PORTS", "")):
    try:
        port_value = int(token)
    except ValueError:
        continue
    if 1 <= port_value <= 65535:
        WHITELIST_PORTS.append(port_value)

WHITELIST_COMMAND_PATTERNS = [
    pattern.lower()
    for pattern in _parse_csv_env(os.getenv("AGENT_SHIELD_WHITELIST_COMMAND_PATTERNS", ""))
]

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
