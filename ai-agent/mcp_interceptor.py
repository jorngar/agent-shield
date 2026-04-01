import asyncio
import concurrent.futures
import ipaddress
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

from agents.base import AgentAdapter
from api_client import BackendClient
from config import (
    BACKEND_DEGRADED_COOLDOWN_SEC,
    BACKEND_URL,
    CLOUD_REVIEW_FAILURE_MODE,
    INTERCEPTABLE_PORTS,
    INTERCEPT_MODE,
    LOCAL_APPROVE_MAX_SCORE,
    LOCAL_DENY_MIN_SCORE,
    LOG_FILE,
    MAX_CONCURRENT_INTERCEPTS,
    OLLAMA_HOST,
    OLLAMA_MODEL,
    PROCESS_SCAN_INTERVAL_SEC,
    WHITELIST_COMMAND_PATTERNS,
    WHITELIST_HOSTS,
    WHITELIST_PORTS,
)
from mcp_detector import create_mcp_detector
from risk_engine import analyze_risk, check_ollama_health


class MCPInterceptor:
    """
    Wraps an AI coding agent and intercepts risky runtime activity.

    Interception sources:
    - MCP-like process spawn commands
    - Child process spawns in broader process-tree modes
    - New established TCP connections for the agent itself and descendant processes
    """

    def __init__(
        self,
        adapter: AgentAdapter,
        backend_url: str = BACKEND_URL,
        verbose: bool = False,
        local_only: bool = False,
    ):
        self._adapter = adapter
        self.agent_name = adapter.name
        self._local_only = local_only
        self.session_id = str(uuid.uuid4())
        self.mcp_detector = create_mcp_detector()
        self.process: Optional[subprocess.Popen] = None
        self.intercepts: List[Dict[str, Any]] = []
        self.blocked_count = 0
        self.approved_count = 0
        self._running = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._process_thread: Optional[threading.Thread] = None
        self._seen_pids: Set[int] = set()
        self._seen_connections: Set[Tuple[int, str, str]] = set()
        self._seen_connection_signatures: Set[Tuple[str, str]] = set()
        self._baseline_remote_endpoints: Set[str] = set()
        self._agent_cmd_tokens: Set[str] = set()
        self._mcp_target_hosts: Set[str] = set()
        self._mcp_target_ports: Set[int] = set()
        self._responses_api_hosts: Set[str] = adapter.responses_api_hosts
        self._intercept_mode = INTERCEPT_MODE
        self._verbose = verbose
        self._log_lock = threading.Lock()
        self._log_file_path = LOG_FILE or ".agent-shield.log"
        self._scheduled_futures: Set[concurrent.futures.Future] = set()
        self._scheduled_futures_lock = threading.Lock()
        self._intercept_semaphore: Optional[asyncio.Semaphore] = None
        self._shield_terminated_root = False
        self._backend_degraded_until = 0.0
        (
            self._whitelist_hosts,
            self._whitelist_ports,
            self._whitelist_endpoints,
        ) = self._build_endpoint_whitelist(
            backend_url=backend_url, ollama_url=OLLAMA_HOST
        )
        self._whitelist_command_patterns = set(WHITELIST_COMMAND_PATTERNS)
        self.backend_client = BackendClient(backend_url)
        self.backend_client.debug_hook = self._log_backend_event

    async def run(self, agent_args: List[str] = None, working_dir: str = ".") -> Dict:
        """
        Run the agent with MCP interception.
        """
        self._refresh_mcp_targets()
        cmd = self._adapter.resolve_command(agent_args)

        self._running = True
        self._loop = asyncio.get_running_loop()
        self._intercept_semaphore = asyncio.Semaphore(MAX_CONCURRENT_INTERCEPTS)
        # Remember the tokens that identify the agent process so that
        # child processes that ARE the agent are not intercepted.
        self._agent_cmd_tokens = self._adapter.build_identity_tokens(cmd)

        # Preflight: check that Ollama is reachable and model is loaded.
        ollama_health = await asyncio.to_thread(check_ollama_health)
        if not ollama_health.get("ok"):
            self._log(
                f"Ollama preflight FAILED: {ollama_health.get('error', 'unknown')}",
                level="ERROR",
                force_console=True,
            )
            self._log(
                "Shield will continue with policy-based fallbacks only "
                "(no LLM risk analysis).",
                level="WARNING",
                force_console=True,
            )
        else:
            warmed = ollama_health.get("model_warmed")
            model_loaded = ollama_health.get("model_loaded")
            latency = ollama_health.get("latency_ms", 0)
            if model_loaded is False:
                self._log(
                    f"WARNING: Model '{OLLAMA_MODEL}' not found in Ollama. "
                    f"Pull it with: ollama pull {OLLAMA_MODEL}",
                    level="WARNING",
                    force_console=True,
                )
            self._log(
                f"Ollama ready (latency={latency}ms, model_warmed={warmed})",
            )

        spawn_env = dict(os.environ)
        if spawn_env.get("TERM", "").strip().lower() == "dumb":
            spawn_env["TERM"] = "xterm-256color"

        try:
            self.process = subprocess.Popen(
                cmd,
                cwd=working_dir,
                env=spawn_env,
                close_fds=True,
            )
        except FileNotFoundError as exc:
            self._log(
                f"Failed to start {self.agent_name} command: {' '.join(cmd)}",
                level="ERROR",
                force_console=True,
            )
            return await self.report_session(
                status_override="failed", codex_exit_code=127, error_message=str(exc)
            )

        self._log(
            f"{self.agent_name} started with PID: {self.process.pid}",
        )

        # Snapshot connections that exist immediately after agent launches.
        # These are inherited from the parent process (shell, npm, etc.)
        # and must be excluded so the shield only monitors connections
        # that the agent itself establishes.
        self._baseline_remote_endpoints = self._snapshot_baseline_connections(
            self.process.pid
        )

        process_thread = threading.Thread(
            target=self._monitor_process_spawns, daemon=True
        )
        self._process_thread = process_thread

        if self.process.stdout is not None:
            stdout_thread = threading.Thread(target=self._monitor_stdout, daemon=True)
            stdout_thread.start()
        if self.process.stderr is not None:
            stderr_thread = threading.Thread(target=self._monitor_stderr, daemon=True)
            stderr_thread.start()
        process_thread.start()

        exit_code = None
        error_message = None
        try:
            exit_code = await self._wait_for_process_exit()
        except KeyboardInterrupt:
            self.stop()
            exit_code = 130
        except Exception as exc:
            self._log(f"Unexpected error while waiting for Codex: {exc}", level="ERROR")
            error_message = str(exc)
            self.stop()
        finally:
            self._running = False
            if self._process_thread:
                self._process_thread.join(
                    timeout=max(PROCESS_SCAN_INTERVAL_SEC * 2, 0.2)
                )
            await self._drain_scheduled_futures()
            self._intercept_semaphore = None
            self._loop = None

        # If the process died from a signal we sent, capture the real exit code
        if exit_code is None and self.process:
            exit_code = self.process.poll()

        return await self.report_session(
            codex_exit_code=exit_code, error_message=error_message
        )

    def _refresh_mcp_targets(self) -> None:
        hosts, ports = self._adapter.discover_mcp_targets()
        self._mcp_target_hosts = hosts
        self._mcp_target_ports = ports

        if hosts or ports:
            self._log(
                f"Loaded MCP targets: hosts={sorted(hosts)} ports={sorted(ports)}"
            )

    @classmethod
    def _host_aliases(cls, host: str) -> Set[str]:
        normalized = host.strip().lower()
        aliases = {normalized}
        if cls._is_local_host(normalized):
            aliases |= {"localhost", "127.0.0.1", "::1", "0.0.0.0", "::"}
        return aliases

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
            for resolved_host in self._resolve_host_addresses(parsed.hostname):
                endpoints.add((resolved_host, port))

        return hosts, ports, endpoints

    @staticmethod
    def _resolve_host_addresses(hostname: str) -> Set[str]:
        resolved: Set[str] = set()
        try:
            for result in socket.getaddrinfo(hostname, None):
                address = result[4][0].strip().lower()
                if address:
                    resolved.add(address)
        except socket.gaierror:
            return resolved
        return resolved

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

    def _is_whitelisted_connection(self, connection: Dict[str, str]) -> bool:
        endpoint_pairs = [
            (connection.get("local_host", ""), connection.get("local_port", "")),
            (connection.get("remote_host", ""), connection.get("remote_port", "")),
        ]

        for host, raw_port in endpoint_pairs:
            try:
                parsed_port = int(raw_port)
            except (TypeError, ValueError):
                parsed_port = None
            if self._is_whitelisted_endpoint(host, parsed_port):
                return True

        return False

    @staticmethod
    def _parse_port(raw_port: Any) -> Optional[int]:
        try:
            parsed_port = int(raw_port)
        except (TypeError, ValueError):
            return None
        if 1 <= parsed_port <= 65535:
            return parsed_port
        return None

    def _matches_intercept_target(self, host: str, port: Optional[int]) -> bool:
        host_aliases = self._host_aliases(host) if host else set()
        if host_aliases & self._mcp_target_hosts:
            return True
        if port is not None and (
            port in self._mcp_target_ports or port in INTERCEPTABLE_PORTS
        ):
            return True
        return False

    def _should_skip_local_ipc_connection(
        self,
        cmdline: str,
        local_host: str,
        local_port: Optional[int],
        remote_host: str,
        remote_port: Optional[int],
    ) -> bool:
        if not (
            self._is_local_host(local_host or "")
            and self._is_local_host(remote_host or "")
        ):
            return False

        is_mcp_process, _, _ = self.mcp_detector.scan_content(cmdline)
        if is_mcp_process:
            return False

        if self._matches_intercept_target(local_host, local_port):
            return False
        if self._matches_intercept_target(remote_host, remote_port):
            return False

        return True

    def _should_skip_internal_network_connection(
        self,
        cmdline: str,
        local_host: str,
        local_port: Optional[int],
        remote_host: str,
        remote_port: Optional[int],
    ) -> bool:
        if not (
            self._is_internal_network_host(local_host or "")
            and self._is_internal_network_host(remote_host or "")
        ):
            return False

        is_mcp_process, _, _ = self.mcp_detector.scan_content(cmdline)
        if is_mcp_process:
            return False

        if self._matches_intercept_target(local_host, local_port):
            return False
        if self._matches_intercept_target(remote_host, remote_port):
            return False

        return True

    def _is_whitelisted_command(self, cmdline: str) -> bool:
        lowered = cmdline.lower()
        return any(pattern in lowered for pattern in self._whitelist_command_patterns)

    def _log(
        self, message: str, level: str = "INFO", force_console: bool = False
    ) -> None:
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

    def _log_backend_event(self, message: str) -> None:
        self._log(f"[BackendClient] {message}", level="DEBUG")

    async def _wait_for_process_exit(self) -> Optional[int]:
        while self.process and self.process.poll() is None:
            await asyncio.sleep(0.1)
        if not self.process:
            return None
        return self.process.poll()

    async def _drain_scheduled_futures(self, timeout: float = 1.0) -> None:
        with self._scheduled_futures_lock:
            scheduled = list(self._scheduled_futures)

        if not scheduled:
            return

        pending = [future for future in scheduled if not future.done()]
        for future in pending:
            future.cancel()

        wrapped = [asyncio.wrap_future(future) for future in pending]
        if not wrapped:
            return

        try:
            await asyncio.wait_for(
                asyncio.gather(*wrapped, return_exceptions=True),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            self._log(
                f"Timed out draining {len(wrapped)} scheduled intercept task(s)",
                level="DEBUG",
            )

    def _schedule_coroutine_threadsafe(
        self, coro: Any, label: str
    ) -> Optional[concurrent.futures.Future]:
        loop = self._loop
        if not self._running or not loop or loop.is_closed():
            try:
                coro.close()
            except Exception:
                pass
            return None

        try:
            future = asyncio.run_coroutine_threadsafe(coro, loop)
        except RuntimeError as exc:
            self._log(f"Skipped scheduling {label}: {exc}", level="DEBUG")
            try:
                coro.close()
            except Exception:
                pass
            return None

        with self._scheduled_futures_lock:
            self._scheduled_futures.add(future)

        def _consume_result(done_future: concurrent.futures.Future) -> None:
            with self._scheduled_futures_lock:
                self._scheduled_futures.discard(done_future)
            try:
                done_future.result()
            except concurrent.futures.CancelledError:
                return
            except Exception as exc:
                self._log(f"Background task {label} failed: {exc}", level="ERROR")

        future.add_done_callback(_consume_result)
        return future

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

    # Patterns that indicate destructive filesystem operations.
    # Checked in ALL intercept modes (including mcp-targets) so that
    # file deletion is never silently allowed.
    _DESTRUCTIVE_CMD_PATTERNS = re.compile(
        r"""(?ix)                          # case-insensitive, verbose
        (?:^|\s|/|;|&&|\|\|)              # preceded by boundary
        (?:
            rm\s+-[a-zA-Z]*[rf]           # rm -rf, rm -f, rm -r, rm -Rf, etc.
          | rm\s+--force                   # rm --force
          | rm\s+--recursive               # rm --recursive
          | rmdir\s                         # rmdir
          | unlink\s                        # unlink
          | shred\s                         # shred
          | srm\s                           # secure-remove
          | find\s.*-delete                 # find ... -delete
          | find\s.*-exec\s+rm             # find ... -exec rm
          | shutil\.rmtree                  # python shutil.rmtree
          | os\.remove                      # python os.remove
          | os\.unlink                      # python os.unlink
          | fs\.rm                          # node fs.rm / fs.rmSync
          | unlinkSync                      # node fs.unlinkSync
          | rimraf                          # npm rimraf
        )
        """,
    )

    def _is_destructive_file_operation(self, cmdline: str) -> Tuple[bool, List[str]]:
        matches = self._DESTRUCTIVE_CMD_PATTERNS.findall(cmdline)
        if matches:
            return True, [m.strip() for m in matches if m.strip()]
        # Also check for rm with path arguments even without -rf flags
        # (bare `rm important_file` is still destructive)
        lowered = cmdline.strip().lower()
        if re.match(r"^rm\s+[^-]", lowered):
            return True, ["rm"]
        return False, []

    def _classify_process_spawn(
        self, cmdline: str
    ) -> Tuple[bool, str, str, Dict[str, Any]]:
        if self._is_whitelisted_command(cmdline):
            return False, "", "whitelisted_command_pattern", {}

        # Skip agent's own runtime processes
        if self._adapter.is_own_process(cmdline):
            return False, "", "agent_internal_process", {}

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

        # Destructive file operations are intercepted in ALL modes
        # (including mcp-targets) and classified at high severity so
        # the local triage can auto-deny without a cloud round-trip.
        is_destructive, matched = self._is_destructive_file_operation(cmdline)
        if is_destructive:
            return (
                True,
                "destructive_file_operation",
                "destructive_command_pattern",
                {
                    "type": "destructive_operation",
                    "matched_patterns": matched,
                    "severity": "high",
                },
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
            out = subprocess.check_output(
                ["pgrep", "-P", str(pid)], text=True, stderr=subprocess.DEVNULL
            ).strip()
            if not out:
                return []
            return [int(x) for x in out.split()]
        except (subprocess.CalledProcessError, FileNotFoundError):
            # Fallback: use ps if pgrep is not available
            return self._ps_children(pid)

    def _ps_children(self, pid: int) -> List[int]:
        try:
            out = subprocess.check_output(
                ["ps", "-o", "pid=", "--ppid", str(pid)],
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
            if not out:
                return []
            return [int(x) for x in out.split()]
        except (subprocess.CalledProcessError, FileNotFoundError):
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
                ["lsof", "-nP", "-p", str(pid), "-iTCP", "-sTCP:ESTABLISHED"],
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

    @classmethod
    def _is_internal_network_host(cls, host: str) -> bool:
        normalized = host.strip().lower()
        if not normalized:
            return False
        if cls._is_local_host(normalized):
            return True

        try:
            address = ipaddress.ip_address(normalized)
        except ValueError:
            return False

        return (
            address.is_private
            or address.is_link_local
            or address.is_reserved
            or address.is_multicast
            or address.is_unspecified
        )

    def _classify_connection_candidate(
        self,
        cmdline: str,
        local_host: str,
        local_port: str,
        remote_host: str,
        remote_port: str,
        process_role: str = "child",
    ) -> Tuple[bool, str, str, Dict[str, Any]]:
        parsed_local_port = self._parse_port(local_port)
        parsed_port = self._parse_port(remote_port)

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

        if self._matches_intercept_target(remote_host, parsed_port):
            return (
                True,
                "mcp_connection_attempt",
                "configured_mcp_target",
                {
                    "type": "mcp_connection",
                    "process_role": process_role,
                    "severity": "high",
                },
            )

        if self._matches_intercept_target(local_host, parsed_local_port):
            return (
                True,
                "mcp_connection_attempt",
                "configured_local_mcp_target",
                {
                    "type": "mcp_connection",
                    "process_role": process_role,
                    "severity": "high",
                },
            )

        if self._should_skip_local_ipc_connection(
            cmdline=cmdline,
            local_host=local_host,
            local_port=parsed_local_port,
            remote_host=remote_host,
            remote_port=parsed_port,
        ):
            return False, "", "local_internal_connection", {}

        if self._should_skip_internal_network_connection(
            cmdline=cmdline,
            local_host=local_host,
            local_port=parsed_local_port,
            remote_host=remote_host,
            remote_port=parsed_port,
        ):
            return False, "", "internal_network_connection", {}

        looks_like_responses_api, responses_reason = (
            self._adapter.is_own_api_connection(
                cmdline=cmdline,
                remote_host=remote_host,
                port=parsed_port,
                process_role=process_role,
            )
        )
        if looks_like_responses_api:
            # Agent's own root-process API connections are its core
            # functionality — auto-allow without risk analysis.
            if process_role == "root" and self._adapter.is_own_process(cmdline):
                return False, "", "agent_own_api_connection", {}
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

    def _kill_process_tree(self, target_pid: int) -> None:
        """
        Terminate a process tree gracefully (SIGTERM first, then SIGKILL).

        When the target is a child process, the root Codex PID is excluded
        from the kill list so a denied child never accidentally tears down
        the entire session.
        """
        codex_pid = self.process.pid if self.process else None

        try:
            descendants = self._get_descendant_pids(target_pid)
        except Exception as exc:
            self._log(
                f"Failed to enumerate descendants of PID {target_pid}: {exc}",
                level="WARNING",
            )
            descendants = set()

        # Build kill list: target + descendants, but never include the root
        # Codex PID unless the target IS the root (explicit shield termination).
        kill_pids = descendants | {target_pid}
        if codex_pid and target_pid != codex_pid:
            kill_pids.discard(codex_pid)

        if not kill_pids:
            return

        # Phase 1: graceful SIGTERM
        for pid in sorted(kill_pids, reverse=True):
            try:
                subprocess.run(["kill", "-15", str(pid)], check=False)
            except Exception:
                pass

        # Brief grace period for processes to clean up
        time.sleep(0.3)

        # Phase 2: SIGKILL only for processes that survived
        for pid in sorted(kill_pids, reverse=True):
            try:
                # Check if still alive before sending SIGKILL
                result = subprocess.run(
                    ["kill", "-0", str(pid)],
                    check=False,
                    capture_output=True,
                )
                if result.returncode == 0:
                    subprocess.run(["kill", "-9", str(pid)], check=False)
                    self._log(
                        f"Process {pid} required SIGKILL after SIGTERM grace period",
                        level="DEBUG",
                    )
            except Exception:
                pass

    def _snapshot_baseline_connections(self, pid: int) -> Set[str]:
        """Capture remote endpoints already open on the process at launch.

        These are inherited from the parent (shell / npm) and should never
        be attributed to Codex activity.
        """
        try:
            network_info = self._inspect_process_network(pid)
        except Exception:
            return set()

        baseline = set()
        for conn in network_info.get("established_connections", []):
            remote_ep = conn.get("remote_endpoint", "")
            if remote_ep:
                baseline.add(remote_ep)

        if baseline:
            self._log(
                f"Baseline connections captured ({len(baseline)} inherited): "
                f"{sorted(baseline)[:10]}{'...' if len(baseline) > 10 else ''}",
                level="DEBUG",
            )

        return baseline

    def _is_baseline_connection(self, remote_endpoint: str) -> bool:
        """Return True if the remote endpoint was present at process launch."""
        return remote_endpoint in self._baseline_remote_endpoints

    @staticmethod
    def _reverse_dns(ip: str) -> Optional[str]:
        """Best-effort reverse DNS lookup. Returns hostname or None."""
        try:
            hostname, _, _ = socket.gethostbyaddr(ip)
            return hostname
        except (socket.herror, socket.gaierror, OSError):
            return None

    def _build_connection_content(
        self,
        pid: int,
        cmdline: str,
        local_endpoint: str,
        remote_endpoint: str,
        remote_host: str,
        connection_scope: str,
        process_role: str,
        action_type: str,
        detection_reason: str,
    ) -> str:
        """
        Build a human-readable content string for connection intercepts
        that gets sent to the backend and displayed in the review UI.
        """
        # Try reverse DNS for the remote IP
        resolved_name = self._reverse_dns(remote_host) if remote_host else None

        # Extract just the executable name from cmdline for brevity
        cmd_short = (
            cmdline.strip().split()[0].split("/")[-1] if cmdline.strip() else "unknown"
        )

        parts = [
            f"Process '{cmd_short}' (PID {pid}, {process_role})",
            f"connected to {remote_endpoint}",
        ]
        if resolved_name and resolved_name != remote_host:
            parts.append(f"({resolved_name})")
        parts.append(f"[{connection_scope}]")
        parts.append(f"| reason: {detection_reason}")
        parts.append(f"| type: {action_type}")

        # Add truncated full command for context
        cmd_preview = cmdline[:200]
        if len(cmdline) > 200:
            cmd_preview += "..."
        parts.append(f"| cmd: {cmd_preview}")

        return " ".join(parts)

    def _record_shield_termination(self, pid: int) -> None:
        if self.process and pid == self.process.pid:
            self._shield_terminated_root = True

    def _should_soft_block_root_connection(self, pid: int, process_role: str) -> bool:
        return bool(self.process and pid == self.process.pid and process_role == "root")

    @staticmethod
    def _coerce_risk_score(value: Any) -> int:
        try:
            score = int(value)
        except (TypeError, ValueError):
            return 50
        return max(0, min(100, score))

    def _resolve_local_triage(self, risk: Dict[str, Any]) -> Tuple[Optional[str], str]:
        recommended_action = str(risk.get("recommended_action", "review")).lower()
        risk_level = str(risk.get("risk_level", "medium")).lower()
        risk_score = self._coerce_risk_score(risk.get("risk_score"))
        flags = {
            str(flag).strip().lower()
            for flag in risk.get("flags", [])
            if str(flag).strip()
        }
        uncertainty_flags = {
            "timeout",
            "service_unavailable",
            "invalid_service_response",
            "parse_error",
            "truncated_response",
            "fallback_policy_applied",
        }
        if flags.intersection(uncertainty_flags):
            return None, "cloud_review_required_uncertain_local_assessment"

        if (
            recommended_action == "approve"
            and risk_level == "low"
            and risk_score <= LOCAL_APPROVE_MAX_SCORE
        ):
            return "approve", "local_low_risk_auto_approve"

        if (
            recommended_action == "deny"
            and risk_level in {"high", "critical"}
            and risk_score >= LOCAL_DENY_MIN_SCORE
        ):
            return "deny", "local_high_risk_auto_deny"

        return None, "cloud_review_required"

    def _is_backend_degraded(self) -> bool:
        return time.time() < self._backend_degraded_until

    def _mark_backend_degraded(self, reason: str) -> None:
        self._backend_degraded_until = time.time() + BACKEND_DEGRADED_COOLDOWN_SEC
        self._log(
            "Backend review degraded; using graceful fallback temporarily: "
            f"reason={reason}; cooldown_sec={BACKEND_DEGRADED_COOLDOWN_SEC}",
            level="WARNING",
        )

    def _resolve_cloud_review_failure_fallback(
        self, failure_reason: str
    ) -> Tuple[str, str]:
        if CLOUD_REVIEW_FAILURE_MODE == "deny":
            return "deny", f"cloud_review_failure_{failure_reason}_deny"
        return "approve", f"cloud_review_failure_{failure_reason}_approve"

    @staticmethod
    def _format_codex_exit_display(
        codex_exit_code: Optional[int], shield_terminated_root: bool
    ) -> str:
        if codex_exit_code is None:
            return "n/a"
        if shield_terminated_root and codex_exit_code < 0:
            return f"blocked by shield (signal {-codex_exit_code})"
        if codex_exit_code < 0:
            # Killed by signal but NOT by the shield — external cause
            return f"killed by signal {-codex_exit_code}"
        return str(codex_exit_code)

    async def _submit_intercept_for_decision(
        self, action_type: str, content: str, risk: Dict[str, Any]
    ) -> Tuple[Optional[str], str, str, str]:
        final_decision = "deny"
        intercept_id = None

        self._log(
            "Intercept submission start: "
            f"action_type={action_type}; "
            f"content_preview={content[:120]}; "
            f"risk_level={risk.get('risk_level')}; "
            f"recommended_action={risk.get('recommended_action')}",
            level="DEBUG",
        )

        local_decision, decision_reason = self._resolve_local_triage(risk)
        if local_decision in {"approve", "deny"}:
            self._log(
                "Local triage resolved intercept without cloud escalation: "
                f"action_type={action_type}; decision={local_decision}; reason={decision_reason}",
                level="DEBUG",
            )
            return None, local_decision, "local", decision_reason

        # In local-only mode, never escalate to backend.
        if self._local_only:
            fallback_decision, fallback_reason = (
                self._resolve_cloud_review_failure_fallback("local_only_mode")
            )
            self._log(
                "LOCAL-ONLY mode: skipping backend escalation: "
                f"action_type={action_type}; decision={fallback_decision}; reason={fallback_reason}",
                level="DEBUG",
            )
            return None, fallback_decision, "local", fallback_reason

        if self._is_backend_degraded():
            fallback_decision, fallback_reason = (
                self._resolve_cloud_review_failure_fallback("backend_degraded")
            )
            self._log(
                "Skipping backend escalation during degraded window: "
                f"action_type={action_type}; decision={fallback_decision}; reason={fallback_reason}",
                level="WARNING",
            )
            return None, fallback_decision, "cloud_fallback", fallback_reason

        self._log(
            "Escalating intercept to backend for cloud review: "
            f"action_type={action_type}; reason={decision_reason}",
            level="DEBUG",
        )

        result = await self.backend_client.submit_intercept(
            session_id=self.session_id,
            agent=self.agent_name,
            action_type=action_type,
            content=content,
            risk=risk,
        )

        intercept_id = result.get("intercept_id")
        self._log(
            "Intercept submission end: "
            f"action_type={action_type}; "
            f"intercept_id={intercept_id}; "
            f"status={result.get('status')}; "
            f"http_status={result.get('http_status')}; "
            f"request_url={result.get('request_url')}; "
            f"error={result.get('error')}",
            level="DEBUG",
        )
        if intercept_id:
            self._log(
                f"Decision polling start: intercept_id={intercept_id}",
                level="DEBUG",
            )
            decision = await self.backend_client.poll_decision(intercept_id)
            final_decision = decision.get("decision", "deny")
            self._log(
                "Decision polling end: "
                f"intercept_id={intercept_id}; "
                f"decision={final_decision}; "
                f"request_url={decision.get('request_url')}; "
                f"timeout={decision.get('timeout', False)}",
                level="DEBUG",
            )
        else:
            self._mark_backend_degraded(
                result.get("error")
                or f"http_status_{result.get('http_status')}"
                or "submit_error"
            )
            fallback_decision, fallback_reason = (
                self._resolve_cloud_review_failure_fallback("submit_error")
            )
            self._log(
                "Intercept submission produced no intercept_id; "
                f"using graceful fallback decision={fallback_decision}; reason={fallback_reason}",
                level="WARNING",
            )
            return None, fallback_decision, "cloud_fallback", fallback_reason

        if decision.get("timeout"):
            self._mark_backend_degraded("decision_timeout")
            fallback_decision, fallback_reason = (
                self._resolve_cloud_review_failure_fallback("decision_timeout")
            )
            self._log(
                "Decision polling timed out; "
                f"using graceful fallback decision={fallback_decision}; reason={fallback_reason}",
                level="WARNING",
            )
            return intercept_id, fallback_decision, "cloud_fallback", fallback_reason

        return intercept_id, final_decision, "cloud", decision_reason

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
                    try:
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
                            self._schedule_coroutine_threadsafe(
                                self._handle_process_spawn(
                                    pid=pid,
                                    cmdline=cmdline,
                                    action_type=action_type,
                                    detection_reason=detection_reason,
                                    metadata=metadata,
                                ),
                                label=f"process_spawn:{pid}",
                            )
                            self._seen_pids.add(pid)
                    except Exception as exc:
                        self._log(
                            f"Error processing PID {pid}: {exc}",
                            level="WARNING",
                        )

                monitored_pids = self._build_monitored_connection_pid_set(
                    root_pid=root_pid,
                    descendants=current_descendants,
                )
                self._inspect_connections_for_pids(
                    root_pid=root_pid, pids=monitored_pids
                )
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
                # Dedup on (process_role, remote_endpoint) so that repeat
                # connections from the same process role to the same remote
                # server (differing only by ephemeral local port) are not
                # re-intercepted.  This prevents the event flood that occurs
                # when Codex opens many short-lived TCP connections to the
                # same host (e.g. API calls, keepalive reconnects).
                signature = (process_role, conn["remote_endpoint"])
                if signature in self._seen_connection_signatures:
                    continue
                self._seen_connection_signatures.add(signature)
                if self._is_baseline_connection(conn["remote_endpoint"]):
                    self._log(
                        "Skipping inherited baseline connection: "
                        f"pid={pid}; role={process_role}; "
                        f"{conn['local_endpoint']} -> {conn['remote_endpoint']}",
                        level="DEBUG",
                    )
                    continue
                if self._is_whitelisted_connection(conn):
                    self._log(
                        "Skipping whitelisted connection: "
                        f"pid={pid}; role={process_role}; "
                        f"{conn['local_endpoint']} -> {conn['remote_endpoint']}",
                        level="DEBUG",
                    )
                    continue
                (
                    is_candidate,
                    action_type,
                    reason,
                    metadata,
                ) = self._classify_connection_candidate(
                    cmdline=cmdline,
                    local_host=conn["local_host"],
                    local_port=conn["local_port"],
                    remote_host=conn["remote_host"],
                    remote_port=conn["remote_port"],
                    process_role=process_role,
                )
                if not is_candidate:
                    continue

                self._schedule_coroutine_threadsafe(
                    self._handle_connection_intercept(
                        pid=pid,
                        cmdline=cmdline,
                        connection=conn,
                        action_type=action_type,
                        detection_reason=reason,
                        metadata=metadata,
                        process_role=process_role,
                    ),
                    label=f"connection:{pid}:{conn['remote_endpoint']}",
                )

    async def _handle_process_spawn(
        self,
        pid: int,
        cmdline: str,
        action_type: str,
        detection_reason: str,
        metadata: Dict[str, Any],
    ) -> None:
        semaphore = self._intercept_semaphore
        if semaphore is None:
            return

        async with semaphore:
            self._log(
                f"Process spawn intercepted start (PID: {pid}, action_type={action_type}, reason={detection_reason})"
            )
            self._log(f"Command: {cmdline[:200]}...", level="DEBUG")

            try:
                network_info = await asyncio.to_thread(
                    self._inspect_process_network, pid
                )
            except Exception as exc:
                self._log(
                    f"Network inspection failed for PID {pid}: {exc}", level="WARNING"
                )
                network_info = {}

            sanitized_cmdline = self._adapter.sanitize_cmdline_for_risk(cmdline)
            try:
                risk = await asyncio.to_thread(
                    analyze_risk,
                    self.agent_name,
                    action_type,
                    sanitized_cmdline,
                    (
                        f"detection_reason={detection_reason}; "
                        f"classification={metadata.get('type', 'unknown')}; "
                        f"listening_ports={network_info.get('listening_ports', [])}; "
                        f"established_connections={network_info.get('established_connections', [])}; "
                        f"listen_raw_preview={network_info.get('listen_raw_preview', [''])[0]}; "
                        f"established_raw_preview={network_info.get('established_raw_preview', [''])[0]}"
                    ),
                )
            except Exception as exc:
                self._log(
                    f"Risk engine failed for process spawn PID {pid}: {exc}; "
                    "defaulting to high-risk assessment",
                    level="ERROR",
                )
                risk = {
                    "risk_level": "high",
                    "risk_score": 80,
                    "recommended_action": "deny",
                    "summary": f"Risk engine unavailable — defaulting to deny ({exc})",
                }

            try:
                (
                    intercept_id,
                    final_decision,
                    decision_source,
                    decision_reason,
                ) = await self._submit_intercept_for_decision(
                    action_type=action_type, content=cmdline, risk=risk
                )
            except Exception as exc:
                self._log(
                    f"Decision submission failed for PID {pid}: {exc}; defaulting to deny",
                    level="ERROR",
                )
                intercept_id = None
                final_decision = "deny"
                decision_source = "local"
                decision_reason = f"decision_pipeline_error: {exc}"

            if final_decision == "deny":
                self._log(
                    f"BLOCKED - {risk.get('summary')} (source={decision_source}, reason={decision_reason})"
                )
                self.blocked_count += 1
                self._record_shield_termination(pid)
                await asyncio.to_thread(self._kill_process_tree, pid)
            else:
                self._log(
                    f"APPROVED (source={decision_source}, reason={decision_reason})"
                )
                self.approved_count += 1

            self._log(
                f"Process spawn intercepted end (PID: {pid}, action_type={action_type}, decision={final_decision}, intercept_id={intercept_id}, source={decision_source})",
                level="DEBUG",
            )

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
                    "decision_source": decision_source,
                    "decision_reason": decision_reason,
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
        semaphore = self._intercept_semaphore
        if semaphore is None:
            return

        async with semaphore:
            local_endpoint = connection.get("local_endpoint", "")
            remote_endpoint = connection.get("remote_endpoint", "")
            remote_host = connection.get("remote_host", "")
            connection_scope = "local" if self._is_local_host(remote_host) else "remote"

            self._log(
                f"Connection intercepted start ({action_type}, PID: {pid}, role={process_role}, {connection_scope}): "
                f"{local_endpoint} -> {remote_endpoint}"
            )

            sanitized_cmdline = self._adapter.sanitize_cmdline_for_risk(cmdline)
            try:
                risk = await asyncio.to_thread(
                    analyze_risk,
                    self.agent_name,
                    action_type,
                    remote_endpoint,
                    (
                        f"pid={pid}; process_role={process_role}; reason={detection_reason}; "
                        f"classification={metadata.get('type', 'unknown')}; scope={connection_scope}; "
                        f"local_endpoint={local_endpoint}; remote_endpoint={remote_endpoint}; "
                        f"process_cmd={sanitized_cmdline[:500]}"
                    ),
                )
            except Exception as exc:
                self._log(
                    f"Risk engine failed for connection PID {pid}: {exc}; "
                    "defaulting to high-risk assessment",
                    level="ERROR",
                )
                risk = {
                    "risk_level": "high",
                    "risk_score": 80,
                    "recommended_action": "deny",
                    "summary": f"Risk engine unavailable — defaulting to deny ({exc})",
                }

            enriched_content = await asyncio.to_thread(
                self._build_connection_content,
                pid=pid,
                cmdline=cmdline,
                local_endpoint=local_endpoint,
                remote_endpoint=remote_endpoint,
                remote_host=remote_host,
                connection_scope=connection_scope,
                process_role=process_role,
                action_type=action_type,
                detection_reason=detection_reason,
            )

            try:
                (
                    intercept_id,
                    final_decision,
                    decision_source,
                    decision_reason,
                ) = await self._submit_intercept_for_decision(
                    action_type=action_type,
                    content=enriched_content,
                    risk=risk,
                )
            except Exception as exc:
                self._log(
                    f"Decision submission failed for connection PID {pid}: {exc}; defaulting to deny",
                    level="ERROR",
                )
                intercept_id = None
                final_decision = "deny"
                decision_source = "local"
                decision_reason = f"decision_pipeline_error: {exc}"

            if final_decision == "deny":
                self.blocked_count += 1
                if self._should_soft_block_root_connection(pid, process_role):
                    self._log(
                        "SOFT-BLOCKED root connection - "
                        f"{risk.get('summary')} (source={decision_source}, reason={decision_reason})"
                    )
                else:
                    self._log(
                        f"BLOCKED connection - {risk.get('summary')} (source={decision_source}, reason={decision_reason})"
                    )
                    self._record_shield_termination(pid)
                    await asyncio.to_thread(self._kill_process_tree, pid)
            else:
                self._log(
                    f"APPROVED connection (source={decision_source}, reason={decision_reason})"
                )
                self.approved_count += 1

            self._log(
                f"Connection intercepted end ({action_type}, PID: {pid}, role={process_role}, decision={final_decision}, intercept_id={intercept_id}, source={decision_source})",
                level="DEBUG",
            )

            self.intercepts.append(
                {
                    "intercept_id": intercept_id,
                    "decision": final_decision,
                    "risk_level": risk.get("risk_level"),
                    "timestamp": datetime.utcnow().isoformat(),
                    "content_preview": enriched_content[:200],
                    "process_pid": pid,
                    "process_type": metadata.get("type", "connection"),
                    "event_type": "network_connection",
                    "connection_scope": connection_scope,
                    "process_role": process_role,
                    "action_type": action_type,
                    "detection_reason": detection_reason,
                    "decision_source": decision_source,
                    "decision_reason": decision_reason,
                    "enforcement_mode": (
                        "soft"
                        if final_decision == "deny"
                        and self._should_soft_block_root_connection(pid, process_role)
                        else "hard"
                    ),
                }
            )

    async def _handle_mcp_attempt(self, content: str) -> None:
        self._log("MCP HTTP proxy payload detected start")

        mcp_info = self.mcp_detector.detect(content) or {"type": "unknown"}
        risk = await asyncio.to_thread(
            analyze_risk,
            self.agent_name,
            "mcp_http_payload",
            content,
            f"MCP type: {mcp_info.get('type', 'unknown')}",
        )

        (
            intercept_id,
            final_decision,
            decision_source,
            decision_reason,
        ) = await self._submit_intercept_for_decision(
            action_type="mcp_http_payload", content=content, risk=risk
        )

        if final_decision == "deny":
            self.blocked_count += 1
        else:
            self.approved_count += 1

        self._log(
            f"MCP HTTP proxy payload detected end (decision={final_decision}, intercept_id={intercept_id}, source={decision_source}, reason={decision_reason})",
            level="DEBUG",
        )

        self.intercepts.append(
            {
                "intercept_id": intercept_id,
                "decision": final_decision,
                "risk_level": risk.get("risk_level"),
                "timestamp": datetime.utcnow().isoformat(),
                "content_preview": content[:100],
                "event_type": "proxy_payload",
                "decision_source": decision_source,
                "decision_reason": decision_reason,
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
        elif self.blocked_count > 0:
            status = "blocked"
        elif (
            self._shield_terminated_root
            and codex_exit_code is not None
            and codex_exit_code < 0
        ):
            # Shield killed root → treat as blocked even if blocked_count
            # wasn't incremented (race condition guard)
            status = "blocked"
        elif codex_exit_code not in (None, 0):
            status = "failed"
        else:
            status = "success"

        codex_exit_display = self._format_codex_exit_display(
            codex_exit_code=codex_exit_code,
            shield_terminated_root=self._shield_terminated_root,
        )

        if not self._local_only:
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
            "codex_exit_display": codex_exit_display,
            "shield_terminated_root": self._shield_terminated_root,
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

        class MCPProxyHandler(http.server.BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                content_length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_length)
                body_str = body.decode("utf-8", errors="ignore")

                interceptor._schedule_coroutine_threadsafe(
                    interceptor._handle_mcp_attempt(body_str),
                    label="proxy_payload",
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
    adapter: AgentAdapter,
    backend_url: str = BACKEND_URL,
    verbose: bool = False,
    local_only: bool = False,
) -> MCPInterceptor:
    return MCPInterceptor(adapter, backend_url, verbose=verbose, local_only=local_only)
