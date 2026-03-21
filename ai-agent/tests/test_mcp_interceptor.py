import asyncio
import os
import sys
import unittest
from unittest.mock import AsyncMock, Mock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from mcp_interceptor import MCPInterceptor


class MCPInterceptorHelperTests(unittest.TestCase):
    def test_resolve_codex_invocation_falls_back_to_npx(self):
        interceptor = MCPInterceptor()
        with patch("mcp_interceptor.shutil.which", return_value=None):
            command = interceptor._resolve_codex_invocation(
                codex_args=None,
                default_command=["codex"],
                default_args=["--help"],
            )

        self.assertEqual(command[:3], ["npx", "-y", "@openai/codex"])
        self.assertEqual(command[3:], ["--help"])

    def test_extract_mcp_targets_from_servers(self):
        servers = [
            {"name": "remote", "url": "https://mcp.example.com:8443/stream"},
            {"name": "local", "transport": {"url": "http://127.0.0.1:3001/mcp"}},
            {"name": "stdio", "command": "npx @modelcontextprotocol/server-filesystem"},
        ]

        hosts, ports = MCPInterceptor._extract_mcp_targets_from_servers(servers)
        self.assertIn("mcp.example.com", hosts)
        self.assertIn("127.0.0.1", hosts)
        self.assertIn(8443, ports)
        self.assertIn(3001, ports)

    def test_parse_established_connections(self):
        lsof_output = """
node 123 user 21u IPv4 0x00 0t0 TCP 127.0.0.1:54000->127.0.0.1:3001 (ESTABLISHED)
node 123 user 22u IPv4 0x00 0t0 TCP 10.0.0.10:54001->104.18.3.2:443 (ESTABLISHED)
"""
        parsed = MCPInterceptor._parse_established_connections(lsof_output)
        self.assertEqual(len(parsed), 2)
        self.assertEqual(parsed[0]["remote_host"], "127.0.0.1")
        self.assertEqual(parsed[0]["remote_port"], "3001")
        self.assertEqual(parsed[1]["remote_host"], "104.18.3.2")

    def test_classify_connection_candidate_from_config(self):
        interceptor = MCPInterceptor()
        interceptor._mcp_target_hosts = {"mcp.example.com"}

        is_candidate, reason = interceptor._classify_connection_candidate(
            cmdline="python worker.py",
            remote_host="mcp.example.com",
            remote_port="443",
        )

        self.assertTrue(is_candidate)
        self.assertEqual(reason, "configured_mcp_host")

    def test_command_references_mcp_target_endpoint(self):
        interceptor = MCPInterceptor()
        interceptor._mcp_target_ports = {3001}

        matched, reason, endpoint = interceptor._command_references_mcp_targets(
            "curl http://127.0.0.1:3001/mcp"
        )
        self.assertTrue(matched)
        self.assertEqual(reason, "shell_references_mcp_port")
        self.assertEqual(endpoint, ("127.0.0.1", 3001))

    def test_classify_process_spawn_strict_mode_intercepts_non_mcp(self):
        interceptor = MCPInterceptor()
        interceptor._intercept_mode = "strict"

        should_intercept, action_type, detection_reason, metadata = (
            interceptor._classify_process_spawn("python harmless_script.py")
        )

        self.assertTrue(should_intercept)
        self.assertEqual(action_type, "shell_process_spawn")
        self.assertEqual(detection_reason, "strict_mode_all_shell")
        self.assertEqual(metadata["type"], "shell_process")

    def test_whitelisted_command_pattern_skips_process_interception(self):
        interceptor = MCPInterceptor()
        interceptor._intercept_mode = "strict"
        interceptor._whitelist_command_patterns = {"localhost:11434"}

        should_intercept, action_type, detection_reason, metadata = (
            interceptor._classify_process_spawn("curl http://localhost:11434/api/chat")
        )

        self.assertFalse(should_intercept)
        self.assertEqual(action_type, "")
        self.assertEqual(detection_reason, "whitelisted_command_pattern")
        self.assertEqual(metadata, {})

    def test_whitelisted_endpoint_skips_connection_interception(self):
        interceptor = MCPInterceptor()
        interceptor._intercept_mode = "strict"
        interceptor._whitelist_ports.add(11434)

        is_candidate, reason = interceptor._classify_connection_candidate(
            cmdline="python worker.py",
            remote_host="127.0.0.1",
            remote_port="11434",
        )

        self.assertFalse(is_candidate)
        self.assertEqual(reason, "whitelisted_endpoint")

    def test_default_whitelist_includes_backend_and_ollama(self):
        interceptor = MCPInterceptor(backend_url="http://localhost:3300")
        self.assertTrue(interceptor._is_whitelisted_endpoint("127.0.0.1", 3300))
        self.assertTrue(interceptor._is_whitelisted_endpoint("localhost", 11434))

    def test_https_backend_endpoint_is_auto_whitelisted(self):
        interceptor = MCPInterceptor(
            backend_url="https://n73h8lxc41.execute-api.ap-southeast-1.amazonaws.com/"
        )
        self.assertTrue(
            interceptor._is_whitelisted_endpoint(
                "n73h8lxc41.execute-api.ap-southeast-1.amazonaws.com", 443
            )
        )


class MCPInterceptorSessionTests(unittest.TestCase):
    @patch.object(MCPInterceptor, "_refresh_mcp_targets")
    @patch("mcp_interceptor.subprocess.Popen")
    def test_run_uses_inherited_stdio_for_tty(
        self, mock_popen, _mock_refresh_targets
    ):
        interceptor = MCPInterceptor()
        interceptor.backend_client.report_session_result = AsyncMock(return_value={"ok": True})

        process = Mock()
        process.pid = 123
        process.stdout = None
        process.stderr = None
        process.wait.return_value = 0
        process.poll.return_value = 0
        mock_popen.return_value = process

        result = asyncio.run(interceptor.run(codex_args=["--help"]))

        self.assertEqual(result["status"], "success")
        launch_calls = [call for call in mock_popen.call_args_list if "cwd" in call.kwargs]
        self.assertTrue(launch_calls)
        kwargs = launch_calls[0].kwargs
        self.assertNotIn("stdin", kwargs)
        self.assertNotIn("stdout", kwargs)
        self.assertNotIn("stderr", kwargs)

    def test_report_session_failed_when_codex_nonzero_exit(self):
        interceptor = MCPInterceptor()
        interceptor.backend_client.report_session_result = AsyncMock(return_value={"ok": True})

        result = asyncio.run(interceptor.report_session(codex_exit_code=2))

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["codex_exit_code"], 2)
        interceptor.backend_client.report_session_result.assert_awaited_once()

    def test_report_session_blocked_on_intercept_denials(self):
        interceptor = MCPInterceptor()
        interceptor.backend_client.report_session_result = AsyncMock(return_value={"ok": True})
        interceptor.blocked_count = 1

        result = asyncio.run(interceptor.report_session(codex_exit_code=0))

        self.assertEqual(result["status"], "blocked")


if __name__ == "__main__":
    unittest.main()
