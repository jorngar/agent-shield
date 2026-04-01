"""HermesAgentAdapter — wraps the Hermes agent."""

import json
import os
import re
from pathlib import Path
from typing import List, Optional, Set, Tuple

from agents.base import AgentAdapter
from agents import register_adapter


@register_adapter("hermes_agent")
class HermesAgentAdapter(AgentAdapter):
    _identity_tokens: Set[str] = set()

    @property
    def name(self) -> str:
        return "hermes-agent"

    def resolve_command(self, user_args: Optional[List[str]]) -> List[str]:
        command = os.getenv("AGENT_SHIELD_HERMES_COMMAND", "hermes")
        args = os.getenv("AGENT_SHIELD_HERMES_ARGS", "")
        cmd = [command]
        if args:
            cmd.extend(args.split())
        if user_args:
            cmd.extend(user_args)
        return cmd

    def is_own_process(self, cmdline: str) -> bool:
        lowered = (cmdline or "").lower()
        if "hermes" not in lowered:
            return False
        parts = lowered.split()
        if not parts:
            return False
        executable = parts[0].rstrip("/").split("/")[-1]
        if executable not in {"node", "npx", "hermes", "python", "python3"}:
            return False
        for token in self._identity_tokens:
            if token in lowered:
                return True
        return executable in {"hermes", "node", "npx", "python", "python3"}

    def build_identity_tokens(self, cmd: List[str]) -> Set[str]:
        tokens: Set[str] = set()
        for arg in cmd:
            lowered = arg.strip().lower()
            if "hermes" in lowered and "/" in lowered:
                tokens.add(lowered)
        self._identity_tokens = tokens
        return tokens

    def sanitize_cmdline_for_risk(self, cmdline: str) -> str:
        return cmdline

    def discover_mcp_targets(self) -> Tuple[Set[str], Set[int]]:
        hosts: Set[str] = set()
        ports: Set[int] = set()

        config_paths = [
            Path.home() / ".hermes" / "config.json",
            Path.home() / ".config" / "hermes" / "config.json",
        ]

        for config_path in config_paths:
            if not config_path.is_file():
                continue
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
            except (json.JSONDecodeError, OSError):
                continue

            servers = config.get("mcpServers", {})
            if not isinstance(servers, dict):
                continue

            for server_conf in servers.values():
                if not isinstance(server_conf, dict):
                    continue
                url = server_conf.get("url") or server_conf.get("endpoint", "")
                if "://" in url:
                    try:
                        from urllib.parse import urlparse

                        parsed = urlparse(url)
                        if parsed.hostname:
                            hosts.add(parsed.hostname.lower())
                        if parsed.port is not None:
                            ports.add(parsed.port)
                    except ValueError:
                        pass
            break

        return hosts, ports

    def is_own_api_connection(
        self,
        cmdline: str,
        remote_host: str,
        port: Optional[int],
        process_role: str,
    ) -> Tuple[bool, str]:
        lowered = (remote_host or "").lower()
        if "hermes" in lowered:
            return True, "hermes_api_host"
        return False, ""

    @property
    def responses_api_hosts(self) -> Set[str]:
        hosts = os.getenv("AGENT_SHIELD_HERMES_API_HOSTS", "")
        return {h.strip().lower() for h in hosts.split(",") if h.strip()}
