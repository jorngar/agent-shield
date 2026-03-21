import os
import shlex
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import urlparse, urlunparse


def _parse_env_assignment(line: str) -> Optional[Tuple[str, str]]:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None
    if stripped.startswith("export "):
        stripped = stripped[7:].strip()
    if "=" not in stripped:
        return None

    key, value = stripped.split("=", 1)
    key = key.strip()
    value = value.strip()
    if not key:
        return None

    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]

    return key, value


def _load_env_file(path: Path) -> None:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return

    preserved_keys = set(os.environ.keys())
    for line in raw.splitlines():
        assignment = _parse_env_assignment(line)
        if not assignment:
            continue
        key, value = assignment
        if key in preserved_keys:
            continue
        os.environ[key] = value


def _load_local_env_files() -> None:
    module_dir = Path(__file__).resolve().parent
    candidate_paths = [module_dir / ".env"]
    cwd_env = Path.cwd() / ".env"
    if cwd_env not in candidate_paths:
        candidate_paths.append(cwd_env)

    for path in candidate_paths:
        _load_env_file(path)


_load_local_env_files()


def _normalize_url(value: str, default: str) -> str:
    normalized = (value or "").strip() or default
    return normalized.rstrip("/")


def _normalize_backend_url(value: str, default: str) -> str:
    normalized = _normalize_url(value, default)
    try:
        parsed = urlparse(normalized)
    except ValueError:
        return normalized

    cleaned_path = parsed.path.rstrip("/")
    if cleaned_path == "/api":
        parsed = parsed._replace(path="")
        return urlunparse(parsed).rstrip("/")
    return normalized


def _normalize_codex_args(tokens: list[str]) -> list[str]:
    legacy_flag_map = {
        "--dangerously-skip-possible-errors": "--dangerously-bypass-approvals-and-sandbox",
    }
    return [legacy_flag_map.get(token, token) for token in tokens]


OLLAMA_HOST = _normalize_url(
    os.getenv("AGENT_SHIELD_OLLAMA_HOST", "http://localhost:11434"),
    "http://localhost:11434",
)
OLLAMA_MODEL = os.getenv("AGENT_SHIELD_OLLAMA_MODEL", "qwen3.5:0.8b")
BACKEND_URL = _normalize_backend_url(
    os.getenv("AGENT_SHIELD_BACKEND_URL", "http://localhost:3000"),
    "http://localhost:3000",
)

# Use local `codex` binary by default and fall back in runtime if unavailable.
CODEX_COMMAND = shlex.split(os.getenv("AGENT_SHIELD_CODEX_COMMAND", "codex"))
CODEX_ARGS = _normalize_codex_args(shlex.split(os.getenv("AGENT_SHIELD_CODEX_ARGS", "")))

INTERCEPT_MODE = os.getenv("AGENT_SHIELD_INTERCEPT_MODE", "process-tree").strip().lower()
if INTERCEPT_MODE not in {"mcp-targets", "process-tree", "strict"}:
    INTERCEPT_MODE = "process-tree"

try:
    PROCESS_SCAN_INTERVAL_SEC = float(
        os.getenv("AGENT_SHIELD_PROCESS_SCAN_INTERVAL_SEC", "0.1")
    )
except ValueError:
    PROCESS_SCAN_INTERVAL_SEC = 0.1
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

RESPONSES_API_HOSTS = [
    host.lower()
    for host in _parse_csv_env(
        os.getenv("AGENT_SHIELD_RESPONSES_API_HOSTS", "api.openai.com")
    )
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
