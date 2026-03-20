import asyncio
import os
import sys
import unittest
from unittest.mock import AsyncMock, patch

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

    def test_is_mcp_connection_candidate_from_config(self):
        interceptor = MCPInterceptor()
        interceptor._mcp_target_hosts = {"mcp.example.com"}

        is_candidate, reason = interceptor._is_mcp_connection_candidate(
            cmdline="python worker.py",
            remote_host="mcp.example.com",
            remote_port="443",
        )

        self.assertTrue(is_candidate)
        self.assertEqual(reason, "configured_mcp_host")


class MCPInterceptorSessionTests(unittest.TestCase):
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
