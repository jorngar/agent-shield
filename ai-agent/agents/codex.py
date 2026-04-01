"""CodexAdapter — wraps OpenAI Codex with all its specific behaviour."""

import re
import shutil
import subprocess
import json
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

from agents.base import AgentAdapter
from agents import register_adapter


@register_adapter("codex")
class CodexAdapter(AgentAdapter):
    # ---- identity ----------------------------------------------------------

    @property
    def name(self) -> str:
        return "codex"

    # ---- launch ------------------------------------------------------------

    def resolve_command(self, user_args: Optional[List[str]]) -> List[str]:
        from config import CODEX_COMMAND, CODEX_ARGS

        command = list(CODEX_COMMAND or ["codex"])
        if not command:
            command = ["codex"]

        if command[0] == "codex" and shutil.which("codex") is None:
            command = ["npx", "-y", "@openai/codex"]

        args = list(user_args if user_args else (CODEX_ARGS or []))
        return command + args

    # ---- process identity --------------------------------------------------

    def is_own_process(self, cmdline: str) -> bool:
        lowered = (cmdline or "").lower()

        if "codex" not in lowered:
            return False

        parts = lowered.split()
        if not parts:
            return False
        executable = parts[0].rstrip("/").split("/")[-1]

        if executable not in {"node", "npx", "codex"}:
            return False

        for token in self._identity_tokens:
            if token in lowered:
                return True

        if executable in {"node", "npx"}:
            script_arg = ""
            for part in parts[1:]:
                if part.startswith("-"):
                    continue
                script_arg = part
                break
            script_basename = script_arg.rstrip("/").split("/")[-1]
            if script_basename == "codex" or "@openai/codex" in script_arg:
                return True

        if executable == "codex":
            return True

        return False

    def build_identity_tokens(self, cmd: List[str]) -> Set[str]:
        tokens: Set[str] = set()
        for arg in cmd:
            lowered = arg.strip().lower()
            if "codex" in lowered and "/" in lowered:
                tokens.add(lowered)
            if "@openai/codex" in lowered:
                tokens.add(lowered)
        self._identity_tokens = tokens
        return tokens

    def sanitize_cmdline_for_risk(self, cmdline: str) -> str:
        return re.sub(r"--dangerously[-\w]*", "(codex-config-flag)", cmdline)

    # ---- MCP discovery -----------------------------------------------------

    def discover_mcp_targets(self) -> Tuple[Set[str], Set[int]]:
        hosts: Set[str] = set()
        ports: Set[int] = set()

        commands = [
            ["codex", "mcp", "list", "--json"],
            ["npx", "-y", "@openai/codex", "mcp", "list", "--json"],
        ]

        servers = []
        for cmd in commands:
            if cmd[0] == "codex" and shutil.which("codex") is None:
                continue
            try:
                output = subprocess.check_output(
                    cmd, text=True, stderr=subprocess.DEVNULL
                ).strip()
                servers = json.loads(output or "[]")
                break
            except (
                subprocess.CalledProcessError,
                FileNotFoundError,
                json.JSONDecodeError,
            ):
                continue

        def consume_url(value: str) -> None:
            try:
                parsed = urlparse(value)
            except ValueError:
                return
            if parsed.scheme not in ("http", "https"):
                return
            if parsed.hostname:
                hosts.add(parsed.hostname.lower())
            if parsed.port is not None:
                ports.add(parsed.port)

        def walk(node: Any) -> None:
            if isinstance(node, dict):
                host_value = node.get("host") or node.get("hostname")
                if isinstance(host_value, str) and host_value.strip():
                    hosts.add(host_value.strip().lower())
                port_value = node.get("port")
                if isinstance(port_value, int):
                    ports.add(port_value)
                elif isinstance(port_value, str) and port_value.isdigit():
                    ports.add(int(port_value))
                for value in node.values():
                    walk(value)
                return
            if isinstance(node, list):
                for value in node:
                    walk(value)
                return
            if isinstance(node, str):
                if "://" in node:
                    consume_url(node.strip())
                return

        walk(servers)
        return hosts, ports

    # ---- API / network classification --------------------------------------

    def is_own_api_connection(
        self,
        cmdline: str,
        remote_host: str,
        port: Optional[int],
        process_role: str,
    ) -> Tuple[bool, str]:
        from mcp_interceptor import MCPInterceptor

        host_aliases = (
            MCPInterceptor._host_aliases(remote_host) if remote_host else set()
        )
        if host_aliases & self.responses_api_hosts:
            return True, "responses_api_host"

        lowered_cmdline = (cmdline or "").lower()
        if "/v1/responses" in lowered_cmdline or "api.openai.com" in lowered_cmdline:
            return True, "responses_api_reference"

        if (
            process_role == "root"
            and self._is_codex_process_static(cmdline)
            and port == 443
            and not MCPInterceptor._is_local_host(remote_host)
        ):
            return True, "codex_root_remote_https"

        return False, ""

    @property
    def responses_api_hosts(self) -> Set[str]:
        from config import RESPONSES_API_HOSTS

        return set(RESPONSES_API_HOSTS)

    # ---- internal helpers --------------------------------------------------

    _identity_tokens: Set[str] = set()

    @staticmethod
    def _is_codex_process_static(cmdline: str) -> bool:
        lowered = (cmdline or "").lower()
        return "codex" in lowered or "@openai/codex" in lowered
