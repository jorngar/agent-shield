import asyncio
import ipaddress
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

from api_client import BackendClient
from config import (
    BACKEND_URL,
    INTERCEPTABLE_PORTS,
    INTERCEPT_MODE,
    LOG_FILE,
    OLLAMA_HOST,
    PROCESS_SCAN_INTERVAL_SEC,
    RESPONSES_API_HOSTS,
    WHITELIST_COMMAND_PATTERNS,
    WHITELIST_HOSTS,
    WHITELIST_PORTS,
)
from mcp_detector import create_mcp_detector
from risk_engine import analyze_risk


class MCPInterceptor:
    """
    Wraps Codex and intercepts risky runtime activity across the Codex process tree.

    Interception sources:
    - MCP-like process spawn commands
    - Child process spawns in broader process-tree modes
    - New established TCP connections for Codex itself and descendant processes
    """

    def __init__(
        self,
        backend_url: str = BACKEND_URL,
        agent_name: str = "codex",
        verbose: bool = False,
    ):
        self.agent_name = agent_name
        self.session_id = str(uuid.uuid4())
        self.backend_client = BackendClient(backend_url)
        self.mcp_detector = create_mcp_detector()
        self.process: Optional[subprocess.Popen] = None
        self.intercepts: List[Dict[str, Any]] = []
        self.blocked_count = 0
        self.approved_count = 0
        self._running = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._seen_pids: Set[int] = set()
        self._seen_connections: Set[Tuple[int, str, str]] = set()
        self._mcp_target_hosts: Set[str] = set()
        self._mcp_target_ports: Set[int] = set()
        self._responses_api_hosts: Set[str] = set(RESPONSES_API_HOSTS)
        self._intercept_mode = INTERCEPT_MODE
        self._verbose = verbose
        self._log_lock = threading.Lock()
        self._log_file_path = LOG_FILE or ".agent-shield.log"
        (
            self._whitelist_hosts,
            self._whitelist_ports,
            self._whitelist_endpoints,
        ) = self._build_endpoint_whitelist(backend_url=backend_url, ollama_url=OLLAMA_HOST)
        self._whitelist_command_patterns = set(WHITELIST_COMMAND_PATTERNS)

    async def run(self, codex_args: List[str] = None, working_dir: str = ".") -> Dict:
        """
        Run Codex with MCP interception.
        """
        from config import CODEX_COMMAND, CODEX_ARGS

        self._refresh_mcp_targets()
        cmd = self._resolve_codex_invocation(
            codex_args=codex_args, default_command=CODEX_COMMAND, default_args=CODEX_ARGS
        )

        self._running = True
        self._loop = asyncio.get_running_loop()
        spawn_env = dict(os.environ)
        if spawn_env.get("TERM", "").strip().lower() == "dumb":
            spawn_env["TERM"] = "xterm-256color"

        try:
            self.process = subprocess.Popen(
                cmd,
                cwd=working_dir,
                env=spawn_env,
            )
        except FileNotFoundError as exc:
            self._log(
                f"Failed to start Codex command: {' '.join(cmd)}",
                level="ERROR",
                force_console=True,
            )
            return await self.report_session(
                status_override="failed", codex_exit_code=127, error_message=str(exc)
            )

        self._log(
            f"Codex started with PID: {self.process.pid}",
        )

        process_thread = threading.Thread(
            target=self._monitor_process_spawns, daemon=True
        )

        if self.process.stdout is not None:
            stdout_thread = threading.Thread(target=self._monitor_stdout, daemon=True)
            stdout_thread.start()
        if self.process.stderr is not None:
            stderr_thread = threading.Thread(target=self._monitor_stderr, daemon=True)
            stderr_thread.start()
        process_thread.start()

        exit_code = None
        try:
            # Do not block the event loop while Codex is running.
            exit_code = await asyncio.to_thread(self.process.wait)
        except KeyboardInterrupt:
            self.stop()
            exit_code = 130
        finally:
            self._running = False

        return await self.report_session(codex_exit_code=exit_code)

    def _resolve_codex_invocation(
        self,
        codex_args: Optional[List[str]],
        default_command: Optional[List[str]],
        default_args: Optional[List[str]],
    ) -> List[str]:
        command = list(default_command or ["codex"])
        if not command:
            command = ["codex"]

        if command[0] == "codex" and shutil.which("codex") is None:
            command = ["npx", "-y", "@openai/codex"]

        args = list(codex_args if codex_args else (default_args or []))
        return command + args

    def _refresh_mcp_targets(self) -> None:
        servers = []
        commands = [
            ["codex", "mcp", "list", "--json"],
            ["npx", "-y", "@openai/codex", "mcp", "list", "--json"],
        ]

        for cmd in commands:
            if cmd[0] == "codex" and shutil.which("codex") is None:
                continue
            try:
                output = subprocess.check_output(
                    cmd, text=True, stderr=subprocess.DEVNULL
                ).strip()
                servers = json.loads(output or "[]")
                break
            except (subprocess.CalledProcessError, FileNotFoundError, json.JSONDecodeError):
                continue

        hosts, ports = self._extract_mcp_targets_from_servers(servers)
        self._mcp_target_hosts = hosts
        self._mcp_target_ports = ports

        if hosts or ports:
            self._log(
                f"Loaded MCP targets: hosts={sorted(hosts)} ports={sorted(ports)}"
            )

    @staticmethod
    def _extract_mcp_targets_from_servers(
        servers: List[Dict[str, Any]],
    ) -> Tuple[Set[str], Set[int]]:
        hosts: Set[str] = set()
        ports: Set[int] = set()

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

    @classmethod
    def _host_aliases(cls, host: str) -> Set[str]:
        normalized = host.strip().lower()
        aliases = {normalized}
        if cls._is_local_host(normalized):
            aliases |= {"localhost", "127.0.0.1", "::1", "0.0.0.0", "::"}
        return aliases

    @staticmethod
    def _is_codex_process(cmdline: str) -> bool:
        lowered = (cmdline or "").lower()
        return "codex" in lowered or "@openai/codex" in lowered

    def _looks_like_responses_api_connection(
        self,
        cmdline: str,
        remote_host: str,
        parsed_port: Optional[int],
        process_role: str,
    ) -> Tuple[bool, str]:
        host_aliases = self._host_aliases(remote_host) if remote_host else set()
        if host_aliases & self._responses_api_hosts:
            return True, "responses_api_host"

        lowered_cmdline = (cmdline or "").lower()
        if "/v1/responses" in lowered_cmdline or "api.openai.com" in lowered_cmdline:
            return True, "responses_api_reference"

        # Codex's own outbound HTTPS traffic is typically its Responses API call path.
        if (
            process_role == "root"
            and self._is_codex_process(cmdline)
            and parsed_port == 443
            and not self._is_local_host(remote_host)
        ):
            return True, "codex_root_remote_https"

        return False, ""

    @staticmethod
    def _build_monitored_connection_pid_set(
        root_pid: int, descendants: Set[int]
    ) -> Set[int]:
        monitored = set(descendants)
        monitored.add(root_pid)
        return monitored

    def _build_endpoint_whitelist(
        self, backend_url: str, ollama_url: str
    ) -> Tuple[Set[str], Set[int], Set[Tuple[str, int]]]:
        hosts: Set[str] = set(WHITELIST_HOSTS)
        ports: Set[int] = set(WHITELIST_PORTS)
        endpoints: Set[Tuple[str, int]] = set()

        for url in [backend_url, ollama_url]:
            try:
                parsed = urlparse(url)
            except ValueError:
                continue
            if not parsed.hostname:
                continue

            port = parsed.port
            if port is None and parsed.scheme == "http":
                port = 80
            if port is None and parsed.scheme == "https":
                port = 443
            if port is None:
                continue

            for alias in self._host_aliases(parsed.hostname):
                endpoints.add((alias, port))

        return hosts, ports, endpoints

    def _is_whitelisted_endpoint(self, host: str, port: Optional[int]) -> bool:
        host_aliases = self._host_aliases(host) if host else set()
        if port is not None and any(
            (alias, port) in self._whitelist_endpoints for alias in host_aliases
        ):
            return True
        if host_aliases & self._whitelist_hosts:
            return True
        if port is not None and port in self._whitelist_ports:
            return True
        return False

    def _is_whitelisted_command(self, cmdline: str) -> bool:
        lowered = cmdline.lower()
        return any(pattern in lowered for pattern in self._whitelist_command_patterns)

    def _log(self, message: str, level: str = "INFO", force_console: bool = False) -> None:
        timestamp = datetime.utcnow().isoformat(timespec="seconds")
        line = f"{timestamp} [{level}] {message}"

        with self._log_lock:
            try:
                with open(self._log_file_path, "a", encoding="utf-8") as logfile:
                    logfile.write(line + "\n")
            except OSError:
                pass

        if self._verbose or force_console:
            print(f"[AgentShield] {message}", file=sys.stderr, flush=True)

    @classmethod
    def _extract_endpoints_from_text(cls, text: str) -> List[Tuple[str, int]]:
        endpoints: Set[Tuple[str, int]] = set()

        for match in re.finditer(r"https?://[^\s'\"<>]+", text, re.IGNORECASE):
            token = match.group(0).strip(".,;")
            try:
                parsed = urlparse(token)
            except ValueError:
                continue
            if parsed.hostname and parsed.port is not None:
                endpoints.add((parsed.hostname.lower(), parsed.port))

        for host, port_str in re.findall(
            r"\b((?:\d{1,3}\.){3}\d{1,3}|[A-Za-z0-9_.\-]+):(\d{1,5})\b", text
        ):
            try:
                port = int(port_str)
            except ValueError:
                continue
            if 1 <= port <= 65535:
                endpoints.add((host.lower(), port))

        return sorted(endpoints)

    def _command_references_mcp_targets(
        self, cmdline: str
    ) -> Tuple[bool, str, Optional[Tuple[str, int]]]:
        for host, port in self._extract_endpoints_from_text(cmdline):
            if self._is_whitelisted_endpoint(host, port):
                continue
            if host in self._mcp_target_hosts:
                return True, "shell_references_mcp_host", (host, port)
            if port in self._mcp_target_ports:
                return True, "shell_references_mcp_port", (host, port)
            if port in INTERCEPTABLE_PORTS:
                return True, "shell_references_known_mcp_port", (host, port)
        return False, "no_mcp_target_reference", None

    def _classify_process_spawn(
        self, cmdline: str
    ) -> Tuple[bool, str, str, Dict[str, Any]]:
        if self._is_whitelisted_command(cmdline):
            return False, "", "whitelisted_command_pattern", {}

        mcp_info = self.mcp_detector.detect(cmdline)
        if mcp_info:
            return (
                True,
                "mcp_process_spawn",
                "mcp_pattern",
                mcp_info,
            )

        target_match, reason, endpoint = self._command_references_mcp_targets(cmdline)
        if target_match:
            metadata = {
                "type": "shell_mcp_target_reference",
                "endpoint": endpoint,
                "matched_patterns": [reason],
                "severity": "high",
            }
            return (
                True,
                "mcp_shell_target_access",
                reason,
                metadata,
            )

        if self._intercept_mode == "process-tree":
            return (
                True,
                "child_process_spawn",
                "process_tree_child_process",
                {
                    "type": "child_process",
                    "matched_patterns": ["process_tree_child_process"],
                    "severity": "medium",
                },
            )

        if self._intercept_mode == "strict":
            return (
                True,
                "shell_process_spawn",
                "strict_mode_all_shell",
                {
                    "type": "shell_process",
                    "matched_patterns": ["strict_mode_all_shell"],
                    "severity": "medium",
                },
            )

        return False, "", "", {}

    def _monitor_stdout(self) -> None:
        if not self.process or self.process.stdout is None:
            return

        for line in iter(self.process.stdout.readline, ""):
            if not self._running:
                break
            cleaned = line.rstrip("\n")
            if cleaned:
                self._log(f"[Codex stdout] {cleaned}", level="DEBUG")

    def _monitor_stderr(self) -> None:
        if not self.process or self.process.stderr is None:
            return

        for line in iter(self.process.stderr.readline, ""):
            if not self._running:
                break
            cleaned = line.rstrip("\n")
            if cleaned:
                self._log(f"[Codex stderr] {cleaned}", level="DEBUG")

    def _pgrep_children(self, pid: int) -> List[int]:
        try:
            out = subprocess.check_output(["pgrep", "-P", str(pid)], text=True).strip()
            if not out:
                return []
            return [int(x) for x in out.split()]
        except subprocess.CalledProcessError:
            return []

    def _get_descendant_pids(self, root_pid: int) -> Set[int]:
        descendants: Set[int] = set()
        queue: List[int] = [root_pid]

        while queue:
            current_pid = queue.pop()
            for child_pid in self._pgrep_children(current_pid):
                if child_pid != root_pid and child_pid not in descendants:
                    descendants.add(child_pid)
                    queue.append(child_pid)

        return descendants

    def _get_process_args(self, pid: int) -> str:
        try:
            return subprocess.check_output(
                ["ps", "-p", str(pid), "-o", "args="], text=True
            ).strip()
        except subprocess.CalledProcessError:
            return ""

    @staticmethod
    def _split_endpoint(endpoint: str) -> Tuple[str, str]:
        host, separator, port = endpoint.rpartition(":")
        if not separator:
            return endpoint.strip().lower(), ""
        return host.strip("[]").strip().lower(), port.strip()

    @classmethod
    def _parse_established_connections(cls, lsof_output: str) -> List[Dict[str, str]]:
        connections: List[Dict[str, str]] = []
        for line in lsof_output.splitlines():
            match = re.search(r"\bTCP\s+(\S+)->(\S+)\s+\(ESTABLISHED\)", line)
            if not match:
                continue

            local_endpoint = match.group(1)
            remote_endpoint = match.group(2)
            local_host, local_port = cls._split_endpoint(local_endpoint)
            remote_host, remote_port = cls._split_endpoint(remote_endpoint)

            connections.append(
                {
                    "local_endpoint": local_endpoint,
                    "remote_endpoint": remote_endpoint,
                    "local_host": local_host,
                    "local_port": local_port,
                    "remote_host": remote_host,
                    "remote_port": remote_port,
                }
            )

        return connections

    def _inspect_process_network(self, pid: int) -> Dict[str, Any]:
        try:
            listen_out = subprocess.check_output(
                ["lsof", "-nP", "-p", str(pid), "-iTCP", "-sTCP:LISTEN"],
                text=True,
            )
        except subprocess.CalledProcessError:
            listen_out = ""

        try:
            established_out = subprocess.check_output(
                ["lsof", "-P", "-p", str(pid), "-iTCP", "-sTCP:ESTABLISHED"],
                text=True,
            )
        except subprocess.CalledProcessError:
            established_out = ""

        listening_ports = sorted(
            {int(match.group(1)) for match in re.finditer(r":(\d+)\b", listen_out)}
        )
        established_connections = self._parse_established_connections(established_out)

        return {
            "listening_ports": [str(port) for port in listening_ports],
            "established_connections": established_connections,
            "listen_raw_preview": [listen_out[:500]],
            "established_raw_preview": [established_out[:500]],
        }

    @staticmethod
    def _is_local_host(host: str) -> bool:
        normalized = host.strip().lower()
        if normalized in {"localhost", "127.0.0.1", "::1", "0.0.0.0", "::"}:
            return True

        try:
            return ipaddress.ip_address(normalized).is_loopback
        except ValueError:
            return False

    def _classify_connection_candidate(
        self,
        cmdline: str,
        remote_host: str,
        remote_port: str,
        process_role: str = "child",
    ) -> Tuple[bool, str, str, Dict[str, Any]]:
        try:
            parsed_port = int(remote_port)
        except (TypeError, ValueError):
            parsed_port = None

        if self._is_whitelisted_endpoint(remote_host, parsed_port):
            return False, "", "whitelisted_endpoint", {}

        is_mcp_process, _, process_type = self.mcp_detector.scan_content(cmdline)
        if is_mcp_process:
            return (
                True,
                "mcp_connection_attempt",
                f"mcp_process:{process_type}",
                {
                    "type": "mcp_connection",
                    "process_role": process_role,
                    "severity": "high",
                },
            )

        if remote_host and remote_host.lower() in self._mcp_target_hosts:
            return (
                True,
                "mcp_connection_attempt",
                "configured_mcp_host",
                {
                    "type": "mcp_connection",
                    "process_role": process_role,
                    "severity": "high",
                },
            )

        if parsed_port is not None and parsed_port in self._mcp_target_ports:
            return (
                True,
                "mcp_connection_attempt",
                "configured_mcp_port",
                {
                    "type": "mcp_connection",
                    "process_role": process_role,
                    "severity": "high",
                },
            )

        if parsed_port is not None and parsed_port in INTERCEPTABLE_PORTS:
            return (
                True,
                "mcp_connection_attempt",
                "known_mcp_proxy_port",
                {
                    "type": "mcp_connection",
                    "process_role": process_role,
                    "severity": "high",
                },
            )

        looks_like_responses_api, responses_reason = (
            self._looks_like_responses_api_connection(
                cmdline=cmdline,
                remote_host=remote_host,
                parsed_port=parsed_port,
                process_role=process_role,
            )
        )
        if looks_like_responses_api:
            return (
                True,
                "responses_api_connection_attempt",
                responses_reason,
                {
                    "type": "responses_api_connection",
                    "process_role": process_role,
                    "severity": "high" if process_role == "root" else "medium",
                },
            )

        if self._intercept_mode == "process-tree":
            return (
                True,
                "agent_connection_attempt",
                f"{process_role}_process_tree_connection",
                {
                    "type": "agent_connection",
                    "process_role": process_role,
                    "severity": "medium",
                },
            )

        if self._intercept_mode == "strict":
            return (
                True,
                "agent_connection_attempt",
                "strict_mode_all_connections",
                {
                    "type": "agent_connection",
                    "process_role": process_role,
                    "severity": "medium",
                },
            )

        return False, "", "non_mcp_connection", {}

    def _kill_process_tree(self, root_pid: int) -> None:
        try:
            descendants = self._get_descendant_pids(root_pid)
            for pid in sorted(descendants, reverse=True):
                subprocess.run(["kill", "-9", str(pid)], check=False)
            subprocess.run(["kill", "-9", str(root_pid)], check=False)
        except Exception:
            pass

    async def _submit_intercept_for_decision(
        self, action_type: str, content: str, risk: Dict[str, Any]
    ) -> Tuple[Optional[str], str]:
        final_decision = "deny"
        intercept_id = None

        result = await self.backend_client.submit_intercept(
            session_id=self.session_id,
            agent=self.agent_name,
            action_type=action_type,
            content=content,
            risk=risk,
        )

        intercept_id = result.get("intercept_id")
        if intercept_id:
            decision = await self.backend_client.poll_decision(intercept_id)
            final_decision = decision.get("decision", "deny")

        return intercept_id, final_decision

    def _monitor_process_spawns(self) -> None:
        if not self.process or not self._loop:
            return

        root_pid = self.process.pid
        try:
            self._seen_pids = self._get_descendant_pids(root_pid)
        except Exception:
            self._seen_pids = set()

        while self._running and self.process and self.process.poll() is None:
            try:
                current_descendants = self._get_descendant_pids(root_pid)
                new_pids = sorted(current_descendants - self._seen_pids)

                for pid in new_pids:
                    cmdline = self._get_process_args(pid)
                    if not cmdline:
                        continue

                    (
                        should_intercept,
                        action_type,
                        detection_reason,
                        metadata,
                    ) = self._classify_process_spawn(cmdline)
                    if should_intercept:
                        asyncio.run_coroutine_threadsafe(
                            self._handle_process_spawn(
                                pid=pid,
                                cmdline=cmdline,
                                action_type=action_type,
                                detection_reason=detection_reason,
                                metadata=metadata,
                            ),
                            self._loop,
                        )
                        self._seen_pids.add(pid)

                monitored_pids = self._build_monitored_connection_pid_set(
                    root_pid=root_pid,
                    descendants=current_descendants,
                )
                self._inspect_connections_for_pids(root_pid=root_pid, pids=monitored_pids)
                self._seen_pids |= set(new_pids)
            except Exception as exc:
                self._log(f"process monitor error: {exc}", level="ERROR")

            time.sleep(PROCESS_SCAN_INTERVAL_SEC)

    def _inspect_connections_for_pids(self, root_pid: int, pids: Set[int]) -> None:
        if not self._loop:
            return

        for pid in sorted(pids):
            cmdline = self._get_process_args(pid)
            if not cmdline:
                continue
            process_role = "root" if pid == root_pid else "child"

            network_info = self._inspect_process_network(pid)
            for conn in network_info.get("established_connections", []):
                key = (pid, conn["local_endpoint"], conn["remote_endpoint"])
                if key in self._seen_connections:
                    continue

                self._seen_connections.add(key)
                (
                    is_candidate,
                    action_type,
                    reason,
                    metadata,
                ) = self._classify_connection_candidate(
                    cmdline=cmdline,
                    remote_host=conn["remote_host"],
                    remote_port=conn["remote_port"],
                    process_role=process_role,
                )
                if not is_candidate:
                    continue

                asyncio.run_coroutine_threadsafe(
                    self._handle_connection_intercept(
                        pid=pid,
                        cmdline=cmdline,
                        connection=conn,
                        action_type=action_type,
                        detection_reason=reason,
                        metadata=metadata,
                        process_role=process_role,
                    ),
                    self._loop,
                )

    async def _handle_process_spawn(
        self,
        pid: int,
        cmdline: str,
        action_type: str,
        detection_reason: str,
        metadata: Dict[str, Any],
    ) -> None:
        self._log(f"Process spawn intercepted (PID: {pid})")
        self._log(f"Command: {cmdline[:200]}...", level="DEBUG")

        network_info = await asyncio.to_thread(self._inspect_process_network, pid)
        risk = await asyncio.to_thread(
            analyze_risk,
            self.agent_name,
            action_type,
            cmdline,
            (
                f"detection_reason={detection_reason}; "
                f"classification={metadata.get('type', 'unknown')}; "
                f"listening_ports={network_info.get('listening_ports', [])}; "
                f"established_connections={network_info.get('established_connections', [])}; "
                f"listen_raw_preview={network_info.get('listen_raw_preview', [''])[0]}; "
                f"established_raw_preview={network_info.get('established_raw_preview', [''])[0]}"
            ),
        )

        intercept_id, final_decision = await self._submit_intercept_for_decision(
            action_type=action_type, content=cmdline, risk=risk
        )

        if final_decision == "deny":
            self._log(f"BLOCKED - {risk.get('summary')}")
            self.blocked_count += 1
            await asyncio.to_thread(self._kill_process_tree, pid)
        else:
            self._log("APPROVED")
            self.approved_count += 1

        self.intercepts.append(
            {
                "intercept_id": intercept_id,
                "decision": final_decision,
                "risk_level": risk.get("risk_level"),
                "timestamp": datetime.utcnow().isoformat(),
                "content_preview": cmdline[:100],
                "process_pid": pid,
                "process_type": metadata.get("type", "unknown"),
                "event_type": "process_spawn",
                "action_type": action_type,
                "detection_reason": detection_reason,
            }
        )

    async def _handle_connection_intercept(
        self,
        pid: int,
        cmdline: str,
        connection: Dict[str, str],
        action_type: str,
        detection_reason: str,
        metadata: Dict[str, Any],
        process_role: str,
    ) -> None:
        local_endpoint = connection.get("local_endpoint", "")
        remote_endpoint = connection.get("remote_endpoint", "")
        remote_host = connection.get("remote_host", "")
        connection_scope = "local" if self._is_local_host(remote_host) else "remote"

        self._log(
            f"Connection intercepted ({action_type}, PID: {pid}, role={process_role}, {connection_scope}): "
            f"{local_endpoint} -> {remote_endpoint}"
        )

        risk = await asyncio.to_thread(
            analyze_risk,
            self.agent_name,
            action_type,
            remote_endpoint,
            (
                f"pid={pid}; process_role={process_role}; reason={detection_reason}; "
                f"classification={metadata.get('type', 'unknown')}; scope={connection_scope}; "
                f"local_endpoint={local_endpoint}; remote_endpoint={remote_endpoint}; "
                f"process_cmd={cmdline[:500]}"
            ),
        )

        intercept_id, final_decision = await self._submit_intercept_for_decision(
            action_type=action_type,
            content=f"{local_endpoint}->{remote_endpoint}",
            risk=risk,
        )

        if final_decision == "deny":
            self._log(f"BLOCKED connection - {risk.get('summary')}")
            self.blocked_count += 1
            await asyncio.to_thread(self._kill_process_tree, pid)
        else:
            self._log("APPROVED connection")
            self.approved_count += 1

        self.intercepts.append(
            {
                "intercept_id": intercept_id,
                "decision": final_decision,
                "risk_level": risk.get("risk_level"),
                "timestamp": datetime.utcnow().isoformat(),
                "content_preview": f"{local_endpoint}->{remote_endpoint}"[:100],
                "process_pid": pid,
                "process_type": metadata.get("type", "connection"),
                "event_type": "network_connection",
                "connection_scope": connection_scope,
                "process_role": process_role,
                "action_type": action_type,
                "detection_reason": detection_reason,
            }
        )

    async def _handle_mcp_attempt(self, content: str) -> None:
        self._log("MCP HTTP proxy payload detected")

        mcp_info = self.mcp_detector.detect(content) or {"type": "unknown"}
        risk = await asyncio.to_thread(
            analyze_risk,
            self.agent_name,
            "mcp_http_payload",
            content,
            f"MCP type: {mcp_info.get('type', 'unknown')}",
        )

        intercept_id, final_decision = await self._submit_intercept_for_decision(
            action_type="mcp_http_payload", content=content, risk=risk
        )

        if final_decision == "deny":
            self.blocked_count += 1
        else:
            self.approved_count += 1

        self.intercepts.append(
            {
                "intercept_id": intercept_id,
                "decision": final_decision,
                "risk_level": risk.get("risk_level"),
                "timestamp": datetime.utcnow().isoformat(),
                "content_preview": content[:100],
                "event_type": "proxy_payload",
            }
        )

    def stop(self) -> None:
        self._running = False
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()

    async def report_session(
        self,
        codex_exit_code: Optional[int] = None,
        status_override: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> Dict[str, Any]:
        if status_override:
            status = status_override
        elif codex_exit_code not in (None, 0):
            status = "failed"
        elif self.blocked_count > 0:
            status = "blocked"
        else:
            status = "success"

        await self.backend_client.report_session_result(
            session_id=self.session_id, status=status, intercepts=self.intercepts
        )

        return {
            "session_id": self.session_id,
            "status": status,
            "total_intercepts": len(self.intercepts),
            "blocked": self.blocked_count,
            "approved": self.approved_count,
            "codex_exit_code": codex_exit_code,
            "error": error_message,
        }


class MCPProxyServer:
    """
    Local proxy server that can receive MCP HTTP payloads and route them to the
    interceptor's risk-analysis flow.
    """

    def __init__(self, interceptor: MCPInterceptor, port: int = 3100):
        self.interceptor = interceptor
        self.port = port
        self.server = None
        self._running = False

    async def start(self) -> None:
        import http.server
        import socketserver

        interceptor = self.interceptor
        loop = asyncio.get_running_loop()

        class MCPProxyHandler(http.server.BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                content_length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_length)
                body_str = body.decode("utf-8", errors="ignore")

                asyncio.run_coroutine_threadsafe(
                    interceptor._handle_mcp_attempt(body_str), loop
                )

                self.send_response(202)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"status":"intercept_submitted"}')

            def log_message(self, format: str, *args: Any) -> None:
                return

        self.server = socketserver.TCPServer(("", self.port), MCPProxyHandler)
        self._running = True
        interceptor._log(f"MCP Proxy listening on port {self.port}", force_console=True)
        await asyncio.to_thread(self.server.serve_forever)

    def stop(self) -> None:
        self._running = False
        if self.server:
            self.server.shutdown()


def create_interceptor(
    backend_url: str = BACKEND_URL,
    agent_name: str = "codex",
    verbose: bool = False,
) -> MCPInterceptor:
    return MCPInterceptor(backend_url, agent_name, verbose=verbose)
