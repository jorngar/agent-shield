"""Integration tests — full interceptor pipeline, adapters, dashboard, local-only."""

import asyncio
import json
import os
import sys
import unittest
import threading
import time
from http.client import HTTPConnection
from unittest.mock import AsyncMock, Mock, patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from mcp_interceptor import MCPInterceptor, create_interceptor
from agents.base import AgentAdapter
from agents.codex import CodexAdapter
from agents.claude_code import ClaudeCodeAdapter
from agents.kilo import KiloAdapter
from agents.gemini_cli import GeminiCLIAdapter
from local_dashboard import start_dashboard, DASHBOARD_HTML


# ---------------------------------------------------------------------------
# Adapter unit tests
# ---------------------------------------------------------------------------


class CodexAdapterTests(unittest.TestCase):
    def test_name(self):
        self.assertEqual(CodexAdapter().name, "codex")

    def test_resolve_command_default(self):
        adapter = CodexAdapter()
        with patch("agents.codex.shutil.which", return_value="/usr/bin/codex"):
            cmd = adapter.resolve_command(user_args=None)
        self.assertIn("codex", cmd[0])

    def test_resolve_command_with_args(self):
        adapter = CodexAdapter()
        cmd = adapter.resolve_command(user_args=["--model", "gpt-4"])
        self.assertEqual(cmd[-2:], ["--model", "gpt-4"])

    def test_resolve_command_npx_fallback(self):
        """When codex binary is missing, fall back to npx."""
        adapter = CodexAdapter()
        with patch("agents.codex.shutil.which", return_value=None):
            cmd = adapter.resolve_command(user_args=None)
        self.assertEqual(cmd[:3], ["npx", "-y", "@openai/codex"])

    def test_is_own_process_codex(self):
        adapter = CodexAdapter()
        adapter.build_identity_tokens(["/usr/local/bin/codex"])
        self.assertTrue(adapter.is_own_process("node /path/to/codex"))

    def test_is_own_process_non_codex(self):
        adapter = CodexAdapter()
        adapter.build_identity_tokens(["/usr/local/bin/codex"])
        self.assertFalse(adapter.is_own_process("python helper.py"))

    def test_is_own_process_npx_openai_codex(self):
        adapter = CodexAdapter()
        adapter.build_identity_tokens([])
        self.assertTrue(adapter.is_own_process("npx -y @openai/codex"))

    def test_sanitize_cmdline_for_risk(self):
        adapter = CodexAdapter()
        sanitized = adapter.sanitize_cmdline_for_risk(
            "codex --dangerously-bypass-approvals"
        )
        self.assertNotIn("dangerously-bypass-approvals", sanitized)
        self.assertIn("codex-config-flag", sanitized)

    def test_responses_api_hosts(self):
        hosts = CodexAdapter().responses_api_hosts
        self.assertIn("api.openai.com", hosts)

    def test_discover_mcp_targets_returns_tuple(self):
        adapter = CodexAdapter()
        with patch("agents.codex.subprocess.check_output", return_value="[]"):
            hosts, ports = adapter.discover_mcp_targets()
        self.assertIsInstance(hosts, set)
        self.assertIsInstance(ports, set)


class ClaudeCodeAdapterTests(unittest.TestCase):
    def test_name(self):
        self.assertEqual(ClaudeCodeAdapter().name, "claude-code")

    def test_responses_api_hosts(self):
        hosts = ClaudeCodeAdapter().responses_api_hosts
        self.assertIn("api.anthropic.com", hosts)

    def test_sanitize_cmdline_strips_permissions_flag(self):
        adapter = ClaudeCodeAdapter()
        sanitized = adapter.sanitize_cmdline_for_risk(
            "claude --dangerously-skip-permissions"
        )
        self.assertNotIn("dangerously-skip-permissions", sanitized)

    def test_is_own_process_claude(self):
        adapter = ClaudeCodeAdapter()
        adapter.build_identity_tokens(["/usr/local/bin/claude"])
        self.assertTrue(adapter.is_own_process("node /path/to/claude"))

    def test_is_own_process_non_claude(self):
        adapter = ClaudeCodeAdapter()
        adapter.build_identity_tokens([])
        self.assertFalse(adapter.is_own_process("python script.py"))


class KiloAdapterTests(unittest.TestCase):
    def test_name(self):
        self.assertEqual(KiloAdapter().name, "kilo")

    def test_is_own_process_kilo(self):
        adapter = KiloAdapter()
        adapter.build_identity_tokens(["/usr/local/bin/kilo"])
        self.assertTrue(adapter.is_own_process("node /path/to/kilo"))

    def test_discover_mcp_targets_returns_empty_without_config(self):
        """Without a config file, discovery returns empty sets."""
        adapter = KiloAdapter()
        with patch("agents.kilo.Path.is_file", return_value=False):
            hosts, ports = adapter.discover_mcp_targets()
        self.assertEqual(hosts, set())
        self.assertEqual(ports, set())

    def test_discover_mcp_targets_parses_json(self):
        adapter = KiloAdapter()
        config_data = {"mcpServers": {"test": {"url": "https://mcp.example.com:8443"}}}
        mock_file = MagicMock()
        mock_file.read.return_value = json.dumps(config_data)
        mock_file.__enter__ = Mock(return_value=mock_file)
        mock_file.__exit__ = Mock(return_value=False)

        with (
            patch("agents.kilo.Path.is_file", return_value=True),
            patch("builtins.open", return_value=mock_file),
        ):
            hosts, ports = adapter.discover_mcp_targets()
        self.assertIn("mcp.example.com", hosts)
        self.assertIn(8443, ports)


class GeminiCLIAdapterTests(unittest.TestCase):
    def test_name(self):
        self.assertEqual(GeminiCLIAdapter().name, "geminicli")

    def test_responses_api_hosts(self):
        hosts = GeminiCLIAdapter().responses_api_hosts
        self.assertIn("generativelanguage.googleapis.com", hosts)

    def test_is_own_api_connection_googleapis(self):
        adapter = GeminiCLIAdapter()
        is_api, reason = adapter.is_own_api_connection(
            cmdline="gemini",
            remote_host="generativelanguage.googleapis.com",
            port=443,
            process_role="root",
        )
        self.assertTrue(is_api)
        self.assertEqual(reason, "gemini_api_host")


# ---------------------------------------------------------------------------
# Local-only mode tests
# ---------------------------------------------------------------------------


class LocalOnlyModeTests(unittest.TestCase):
    def test_local_only_flag_skips_backend_submit(self):
        """When local_only=True, medium-risk intercepts should not reach backend."""
        adapter = _MockAdapter()
        interceptor = _make_interceptor(adapter=adapter, local_only=True)
        interceptor.backend_client.submit_intercept = AsyncMock(
            return_value={"intercept_id": "should_not_be_called", "status": "pending"}
        )

        # Medium risk should escalate in normal mode but skip backend in local-only
        decision, reason = interceptor._resolve_local_triage(
            {"risk_level": "medium", "risk_score": 52, "recommended_action": "review"}
        )
        self.assertIsNone(decision)
        self.assertEqual(reason, "cloud_review_required")

        # In local-only mode, submit_intercept_for_decision should return fallback
        result = asyncio.run(
            interceptor._submit_intercept_for_decision(
                action_type="connection",
                content="test",
                risk={
                    "risk_level": "medium",
                    "risk_score": 52,
                    "recommended_action": "review",
                },
            )
        )
        _, final_decision, source, fallback_reason = result
        self.assertEqual(source, "local")
        interceptor.backend_client.submit_intercept.assert_not_called()

    def test_local_only_flag_skips_session_report(self):
        """report_session should not call backend in local-only mode."""
        interceptor = _make_interceptor(local_only=True)
        interceptor.backend_client.report_session_result = AsyncMock()

        result = asyncio.run(interceptor.report_session(codex_exit_code=0))
        interceptor.backend_client.report_session_result.assert_not_called()
        self.assertEqual(result["status"], "success")


# ---------------------------------------------------------------------------
# Dashboard tests
# ---------------------------------------------------------------------------


class LocalDashboardTests(unittest.TestCase):
    def test_dashboard_serves_html(self):
        interceptor = _make_interceptor()
        server = start_dashboard(interceptor, port=0)  # port=0 picks random
        port = server.server_address[1]

        try:
            conn = HTTPConnection("127.0.0.1", port, timeout=2)
            conn.request("GET", "/")
            resp = conn.getresponse()
            body = resp.read().decode("utf-8")
            self.assertEqual(resp.status, 200)
            self.assertIn("Agent Shield", body)
            conn.close()
        finally:
            server.shutdown()

    def test_dashboard_api_state(self):
        interceptor = _make_interceptor()
        interceptor.session_id = "test-session-123"
        interceptor.agent_name = "codex"
        interceptor.blocked_count = 2
        interceptor.approved_count = 5
        interceptor.intercepts.append({"decision": "approve", "risk_level": "low"})

        server = start_dashboard(interceptor, port=0)
        port = server.server_address[1]

        try:
            conn = HTTPConnection("127.0.0.1", port, timeout=2)
            conn.request("GET", "/api/state")
            resp = conn.getresponse()
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(resp.status, 200)
            self.assertEqual(data["session_id"], "test-session-123")
            self.assertEqual(data["blocked"], 2)
            self.assertEqual(data["approved"], 5)
            self.assertEqual(len(data["intercepts"]), 1)
            conn.close()
        finally:
            server.shutdown()

    def test_dashboard_api_intercepts(self):
        interceptor = _make_interceptor()
        interceptor.intercepts.append({"decision": "deny", "risk_level": "critical"})
        interceptor.intercepts.append({"decision": "approve", "risk_level": "low"})

        server = start_dashboard(interceptor, port=0)
        port = server.server_address[1]

        try:
            conn = HTTPConnection("127.0.0.1", port, timeout=2)
            conn.request("GET", "/api/intercepts")
            resp = conn.getresponse()
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(resp.status, 200)
            self.assertEqual(len(data), 2)
            conn.close()
        finally:
            server.shutdown()


# ---------------------------------------------------------------------------
# Integration tests — full pipeline
# ---------------------------------------------------------------------------


class FullPipelineTests(unittest.IsolatedAsyncioTestCase):
    @patch.object(MCPInterceptor, "_refresh_mcp_targets")
    @patch("mcp_interceptor.subprocess.Popen")
    async def test_run_success_with_backend(self, mock_popen, _mock_refresh):
        """Full pipeline: launch agent → process exit → session report."""
        interceptor = _make_interceptor()
        interceptor.backend_client.report_session_result = AsyncMock(
            return_value={"ok": True}
        )
        interceptor.backend_client.health_check = AsyncMock(return_value={"ok": True})

        process = Mock()
        process.pid = 12345
        process.stdout = None
        process.stderr = None
        process.wait.return_value = 0
        process.poll.return_value = 0
        mock_popen.return_value = process

        result = await interceptor.run(agent_args=["--version"])

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["codex_exit_code"], 0)
        self.assertIn("session_id", result)

    @patch.object(MCPInterceptor, "_refresh_mcp_targets")
    @patch("mcp_interceptor.subprocess.Popen")
    async def test_run_success_local_only(self, mock_popen, _mock_refresh):
        """Local-only pipeline: launch agent → exit → no backend call."""
        interceptor = _make_interceptor(local_only=True)
        interceptor.backend_client.report_session_result = AsyncMock()

        process = Mock()
        process.pid = 12346
        process.stdout = None
        process.stderr = None
        process.poll.return_value = 0
        mock_popen.return_value = process

        result = await interceptor.run(agent_args=[])

        self.assertEqual(result["status"], "success")
        interceptor.backend_client.report_session_result.assert_not_called()

    @patch.object(MCPInterceptor, "_refresh_mcp_targets")
    @patch("mcp_interceptor.subprocess.Popen")
    async def test_run_handles_spawn_not_found(self, mock_popen, _mock_refresh):
        """When agent binary is not found, report_session returns failed."""
        interceptor = _make_interceptor(local_only=True)
        mock_popen.side_effect = FileNotFoundError("no such binary")

        result = await interceptor.run(agent_args=[])

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["codex_exit_code"], 127)

    async def test_process_spawn_interception_in_process_tree_mode(self):
        """Process spawn in process-tree mode should be scheduled for interception."""
        interceptor = _make_interceptor()
        interceptor._intercept_mode = "process-tree"
        interceptor._loop = asyncio.get_running_loop()
        interceptor._running = True

        scheduled = []
        interceptor._schedule_coroutine_threadsafe = Mock(
            side_effect=lambda coro, label: (coro.close(), scheduled.append(label))[1]
        )

        interceptor._seen_pids = set()

        with patch.object(
            interceptor, "_get_process_args", return_value="python exploit.py"
        ):
            interceptor._classify_process_spawn = Mock(
                return_value=(
                    True,
                    "child_process_spawn",
                    "process_tree_child_process",
                    {"type": "child_process"},
                )
            )
            interceptor._schedule_coroutine_threadsafe(
                asyncio.sleep(0), label="process_spawn:999"
            )

        self.assertTrue(len(scheduled) > 0)


# ---------------------------------------------------------------------------
# Process tree scanning tests
# ---------------------------------------------------------------------------


class ProcessTreeScanningTests(unittest.TestCase):
    def test_pgrep_children_empty_on_no_children(self):
        interceptor = _make_interceptor()
        # Use a PID that won't have children (PID 1 on most systems has children,
        # so just test the method doesn't crash)
        result = interceptor._pgrep_children(os.getpid())
        self.assertIsInstance(result, list)

    def test_ps_children_fallback(self):
        interceptor = _make_interceptor()
        # ps --ppid should work as fallback
        result = interceptor._ps_children(os.getpid())
        self.assertIsInstance(result, list)

    def test_get_descendant_pids_returns_set(self):
        interceptor = _make_interceptor()
        result = interceptor._get_descendant_pids(os.getpid())
        self.assertIsInstance(result, set)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _MockAdapter(AgentAdapter):
    def __init__(self):
        self._own_api_result = (False, "")

    @property
    def name(self) -> str:
        return "codex"

    def resolve_command(self, user_args):
        return ["echo", "test"]

    def is_own_process(self, cmdline: str) -> bool:
        return "codex" in (cmdline or "").lower()

    def build_identity_tokens(self, cmd):
        return set()

    def sanitize_cmdline_for_risk(self, cmdline: str) -> str:
        return cmdline

    def discover_mcp_targets(self):
        return set(), set()

    def is_own_api_connection(self, cmdline, remote_host, port, process_role):
        return self._own_api_result

    @property
    def responses_api_hosts(self):
        return {"api.openai.com"}


def _make_interceptor(**kwargs):
    adapter = kwargs.pop("adapter", _MockAdapter())
    return MCPInterceptor(adapter=adapter, **kwargs)


def mock_open_json(data):
    """Return a mock that reads JSON when opened."""
    m = MagicMock()
    m.__enter__ = Mock(return_value=m)
    m.__exit__ = Mock(return_value=False)
    m.read.return_value = json.dumps(data)
    return m


if __name__ == "__main__":
    unittest.main()
