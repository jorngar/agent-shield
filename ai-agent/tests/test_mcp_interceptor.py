import asyncio
import os
import sys
import unittest
from unittest.mock import AsyncMock, Mock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from mcp_interceptor import MCPInterceptor


class MCPInterceptorHelperTests(unittest.TestCase):
    def test_default_intercept_mode_is_process_tree(self):
        with patch("mcp_interceptor.INTERCEPT_MODE", "process-tree"):
            interceptor = MCPInterceptor()
        self.assertEqual(interceptor._intercept_mode, "process-tree")

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
        interceptor._intercept_mode = "mcp-targets"
        interceptor._mcp_target_hosts = {"mcp.example.com"}

        is_candidate, action_type, reason, metadata = interceptor._classify_connection_candidate(
            cmdline="python worker.py",
            local_host="10.0.0.1",
            local_port="54000",
            remote_host="mcp.example.com",
            remote_port="443",
        )

        self.assertTrue(is_candidate)
        self.assertEqual(action_type, "mcp_connection_attempt")
        self.assertEqual(reason, "configured_mcp_target")
        self.assertEqual(metadata["type"], "mcp_connection")

    def test_command_references_mcp_target_endpoint(self):
        interceptor = MCPInterceptor()
        interceptor._mcp_target_ports = {3001}

        matched, reason, endpoint = interceptor._command_references_mcp_targets(
            "curl http://127.0.0.1:3001/mcp"
        )
        self.assertTrue(matched)
        self.assertEqual(reason, "shell_references_mcp_port")
        self.assertEqual(endpoint, ("127.0.0.1", 3001))

    def test_classify_process_spawn_process_tree_mode_intercepts_non_mcp(self):
        interceptor = MCPInterceptor()
        interceptor._intercept_mode = "process-tree"

        should_intercept, action_type, detection_reason, metadata = (
            interceptor._classify_process_spawn("python harmless_script.py")
        )

        self.assertTrue(should_intercept)
        self.assertEqual(action_type, "child_process_spawn")
        self.assertEqual(detection_reason, "process_tree_child_process")
        self.assertEqual(metadata["type"], "child_process")

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

        is_candidate, action_type, reason, metadata = interceptor._classify_connection_candidate(
            cmdline="python worker.py",
            local_host="127.0.0.1",
            local_port="54000",
            remote_host="127.0.0.1",
            remote_port="11434",
        )

        self.assertFalse(is_candidate)
        self.assertEqual(action_type, "")
        self.assertEqual(reason, "whitelisted_endpoint")
        self.assertEqual(metadata, {})

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

    def test_whitelisted_connection_skips_local_ollama_server_side_socket(self):
        interceptor = MCPInterceptor()
        connection = {
            "local_endpoint": "localhost:11434",
            "remote_endpoint": "localhost:50351",
            "local_host": "localhost",
            "local_port": "11434",
            "remote_host": "localhost",
            "remote_port": "50351",
        }

        self.assertTrue(interceptor._is_whitelisted_connection(connection))

    @patch("mcp_interceptor.socket.getaddrinfo")
    def test_backend_hostname_resolution_is_added_to_whitelist(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = [
            (0, 0, 0, "", ("18.97.36.76", 0)),
        ]

        interceptor = MCPInterceptor(
            backend_url="https://n73h8lxc41.execute-api.ap-southeast-1.amazonaws.com"
        )

        self.assertTrue(interceptor._is_whitelisted_endpoint("18.97.36.76", 443))

    def test_root_codex_responses_api_connection_is_intercepted(self):
        interceptor = MCPInterceptor()
        interceptor._intercept_mode = "process-tree"

        is_candidate, action_type, reason, metadata = interceptor._classify_connection_candidate(
            cmdline="codex",
            local_host="10.0.0.10",
            local_port="54000",
            remote_host="104.18.3.2",
            remote_port="443",
            process_role="root",
        )

        self.assertTrue(is_candidate)
        self.assertEqual(action_type, "responses_api_connection_attempt")
        self.assertEqual(reason, "codex_root_remote_https")
        self.assertEqual(metadata["type"], "responses_api_connection")
        self.assertEqual(metadata["process_role"], "root")

    def test_process_tree_mode_intercepts_generic_child_connection(self):
        interceptor = MCPInterceptor()
        interceptor._intercept_mode = "process-tree"

        is_candidate, action_type, reason, metadata = interceptor._classify_connection_candidate(
            cmdline="npx @playwright/mcp",
            local_host="10.0.0.10",
            local_port="54000",
            remote_host="registry.npmjs.org",
            remote_port="443",
            process_role="child",
        )

        self.assertTrue(is_candidate)
        self.assertEqual(action_type, "agent_connection_attempt")
        self.assertEqual(reason, "child_process_tree_connection")
        self.assertEqual(metadata["type"], "agent_connection")

    def test_process_tree_mode_skips_generic_local_loopback_ipc(self):
        interceptor = MCPInterceptor()
        interceptor._intercept_mode = "process-tree"

        is_candidate, action_type, reason, metadata = interceptor._classify_connection_candidate(
            cmdline="codex",
            local_host="127.0.0.1",
            local_port="63468",
            remote_host="127.0.0.1",
            remote_port="52942",
            process_role="root",
        )

        self.assertFalse(is_candidate)
        self.assertEqual(action_type, "")
        self.assertEqual(reason, "local_internal_connection")
        self.assertEqual(metadata, {})

    def test_process_tree_mode_skips_internal_link_local_network_connection(self):
        interceptor = MCPInterceptor()
        interceptor._intercept_mode = "process-tree"

        is_candidate, action_type, reason, metadata = interceptor._classify_connection_candidate(
            cmdline="codex",
            local_host="fe80::4c78:c35d:8980:e67",
            local_port="1024",
            remote_host="fe80::c3e6:8785:8637:ea52",
            remote_port="1024",
            process_role="root",
        )

        self.assertFalse(is_candidate)
        self.assertEqual(action_type, "")
        self.assertEqual(reason, "internal_network_connection")
        self.assertEqual(metadata, {})

    def test_process_tree_mode_skips_private_ipv4_internal_network_connection(self):
        interceptor = MCPInterceptor()
        interceptor._intercept_mode = "process-tree"

        is_candidate, action_type, reason, metadata = interceptor._classify_connection_candidate(
            cmdline="python helper.py",
            local_host="192.168.1.10",
            local_port="55000",
            remote_host="192.168.1.20",
            remote_port="9000",
            process_role="child",
        )

        self.assertFalse(is_candidate)
        self.assertEqual(action_type, "")
        self.assertEqual(reason, "internal_network_connection")
        self.assertEqual(metadata, {})

    def test_build_monitored_connection_pid_set_includes_root_process(self):
        monitored = MCPInterceptor._build_monitored_connection_pid_set(
            root_pid=10,
            descendants={11, 12},
        )

        self.assertEqual(monitored, {10, 11, 12})

    def test_local_triage_auto_approves_low_risk_actions(self):
        interceptor = MCPInterceptor()

        decision, reason = interceptor._resolve_local_triage(
            {
                "risk_level": "low",
                "risk_score": 18,
                "recommended_action": "approve",
            }
        )

        self.assertEqual(decision, "approve")
        self.assertEqual(reason, "local_low_risk_auto_approve")

    def test_local_triage_auto_denies_high_risk_actions(self):
        interceptor = MCPInterceptor()

        decision, reason = interceptor._resolve_local_triage(
            {
                "risk_level": "critical",
                "risk_score": 97,
                "recommended_action": "deny",
            }
        )

        self.assertEqual(decision, "deny")
        self.assertEqual(reason, "local_high_risk_auto_deny")

    def test_local_triage_escalates_review_band(self):
        interceptor = MCPInterceptor()

        decision, reason = interceptor._resolve_local_triage(
            {
                "risk_level": "medium",
                "risk_score": 52,
                "recommended_action": "review",
            }
        )

        self.assertIsNone(decision)
        self.assertEqual(reason, "cloud_review_required")


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

    def test_report_session_blocked_takes_precedence_over_shield_kill_exit(self):
        interceptor = MCPInterceptor()
        interceptor.backend_client.report_session_result = AsyncMock(return_value={"ok": True})
        interceptor.blocked_count = 1
        interceptor._shield_terminated_root = True

        result = asyncio.run(interceptor.report_session(codex_exit_code=-9))

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["codex_exit_code"], -9)
        self.assertEqual(result["codex_exit_display"], "blocked by shield (signal 9)")
        self.assertTrue(result["shield_terminated_root"])

    def test_record_shield_termination_only_marks_root_process(self):
        interceptor = MCPInterceptor()
        interceptor.process = Mock(pid=100)

        interceptor._record_shield_termination(101)
        self.assertFalse(interceptor._shield_terminated_root)

        interceptor._record_shield_termination(100)
        self.assertTrue(interceptor._shield_terminated_root)


class MCPInterceptorAsyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_submit_intercept_for_decision_skips_backend_on_local_approve(self):
        interceptor = MCPInterceptor()
        interceptor.backend_client.submit_intercept = AsyncMock()
        interceptor.backend_client.poll_decision = AsyncMock()

        result = await interceptor._submit_intercept_for_decision(
            action_type="agent_connection_attempt",
            content="127.0.0.1:1->1.1.1.1:443",
            risk={
                "risk_level": "low",
                "risk_score": 10,
                "recommended_action": "approve",
            },
        )

        self.assertEqual(
            result,
            (None, "approve", "local", "local_low_risk_auto_approve"),
        )
        interceptor.backend_client.submit_intercept.assert_not_awaited()
        interceptor.backend_client.poll_decision.assert_not_awaited()

    async def test_submit_intercept_for_decision_escalates_review_to_cloud(self):
        interceptor = MCPInterceptor()
        interceptor.backend_client.submit_intercept = AsyncMock(
            return_value={"intercept_id": "abc", "status": "pending"}
        )
        interceptor.backend_client.poll_decision = AsyncMock(
            return_value={"intercept_id": "abc", "decision": "approve"}
        )

        result = await interceptor._submit_intercept_for_decision(
            action_type="agent_connection_attempt",
            content="127.0.0.1:1->1.1.1.1:443",
            risk={
                "risk_level": "medium",
                "risk_score": 45,
                "recommended_action": "review",
            },
        )

        self.assertEqual(result, ("abc", "approve", "cloud", "cloud_review_required"))
        interceptor.backend_client.submit_intercept.assert_awaited_once()
        interceptor.backend_client.poll_decision.assert_awaited_once_with("abc")

    async def test_submit_intercept_for_decision_gracefully_approves_on_submit_error(self):
        interceptor = MCPInterceptor()
        interceptor.backend_client.submit_intercept = AsyncMock(
            return_value={"intercept_id": None, "status": "error", "http_status": 502}
        )
        interceptor.backend_client.poll_decision = AsyncMock()

        result = await interceptor._submit_intercept_for_decision(
            action_type="agent_connection_attempt",
            content="127.0.0.1:1->1.1.1.1:443",
            risk={
                "risk_level": "medium",
                "risk_score": 45,
                "recommended_action": "review",
            },
        )

        self.assertEqual(
            result,
            (None, "approve", "cloud_fallback", "cloud_review_failure_submit_error_approve"),
        )
        self.assertGreater(interceptor._backend_degraded_until, 0.0)
        interceptor.backend_client.poll_decision.assert_not_awaited()

    async def test_submit_intercept_for_decision_gracefully_approves_on_timeout(self):
        interceptor = MCPInterceptor()
        interceptor.backend_client.submit_intercept = AsyncMock(
            return_value={"intercept_id": "abc", "status": "pending"}
        )
        interceptor.backend_client.poll_decision = AsyncMock(
            return_value={"intercept_id": "abc", "decision": "deny", "timeout": True}
        )

        result = await interceptor._submit_intercept_for_decision(
            action_type="agent_connection_attempt",
            content="127.0.0.1:1->1.1.1.1:443",
            risk={
                "risk_level": "medium",
                "risk_score": 45,
                "recommended_action": "review",
            },
        )

        self.assertEqual(
            result,
            ("abc", "approve", "cloud_fallback", "cloud_review_failure_decision_timeout_approve"),
        )

    async def test_submit_intercept_for_decision_skips_backend_during_degraded_window(self):
        interceptor = MCPInterceptor()
        interceptor._backend_degraded_until = 10**12
        interceptor.backend_client.submit_intercept = AsyncMock()
        interceptor.backend_client.poll_decision = AsyncMock()

        result = await interceptor._submit_intercept_for_decision(
            action_type="agent_connection_attempt",
            content="127.0.0.1:1->1.1.1.1:443",
            risk={
                "risk_level": "medium",
                "risk_score": 45,
                "recommended_action": "review",
            },
        )

        self.assertEqual(
            result,
            (None, "approve", "cloud_fallback", "cloud_review_failure_backend_degraded_approve"),
        )
        interceptor.backend_client.submit_intercept.assert_not_awaited()
        interceptor.backend_client.poll_decision.assert_not_awaited()

    async def test_handle_connection_intercept_soft_blocks_root_deny_without_kill(self):
        interceptor = MCPInterceptor()
        interceptor.process = Mock(pid=100)
        interceptor._intercept_semaphore = asyncio.Semaphore(1)
        interceptor._submit_intercept_for_decision = AsyncMock(
            return_value=(None, "deny", "local", "local_high_risk_auto_deny")
        )
        interceptor._kill_process_tree = Mock()

        connection = {
            "local_endpoint": "10.0.0.10:54000",
            "remote_endpoint": "104.18.3.2:443",
            "local_host": "10.0.0.10",
            "local_port": "54000",
            "remote_host": "104.18.3.2",
            "remote_port": "443",
        }

        with patch(
            "mcp_interceptor.analyze_risk",
            return_value={
                "risk_level": "critical",
                "risk_score": 95,
                "summary": "danger",
                "recommended_action": "deny",
            },
        ):
            await interceptor._handle_connection_intercept(
                pid=100,
                cmdline="codex",
                connection=connection,
                action_type="agent_connection_attempt",
                detection_reason="root_process_tree_connection",
                metadata={"type": "agent_connection"},
                process_role="root",
            )

        interceptor._kill_process_tree.assert_not_called()
        self.assertEqual(interceptor.blocked_count, 1)
        self.assertFalse(interceptor._shield_terminated_root)
        self.assertEqual(interceptor.intercepts[-1]["enforcement_mode"], "soft")

    async def test_handle_connection_intercept_hard_blocks_child_deny(self):
        interceptor = MCPInterceptor()
        interceptor.process = Mock(pid=100)
        interceptor._intercept_semaphore = asyncio.Semaphore(1)
        interceptor._submit_intercept_for_decision = AsyncMock(
            return_value=(None, "deny", "local", "local_high_risk_auto_deny")
        )
        interceptor._kill_process_tree = Mock()

        connection = {
            "local_endpoint": "10.0.0.10:54000",
            "remote_endpoint": "104.18.3.2:443",
            "local_host": "10.0.0.10",
            "local_port": "54000",
            "remote_host": "104.18.3.2",
            "remote_port": "443",
        }

        with patch(
            "mcp_interceptor.analyze_risk",
            return_value={
                "risk_level": "critical",
                "risk_score": 95,
                "summary": "danger",
                "recommended_action": "deny",
            },
        ):
            await interceptor._handle_connection_intercept(
                pid=101,
                cmdline="python helper.py",
                connection=connection,
                action_type="agent_connection_attempt",
                detection_reason="child_process_tree_connection",
                metadata={"type": "agent_connection"},
                process_role="child",
            )

        interceptor._kill_process_tree.assert_called_once_with(101)
        self.assertEqual(interceptor.blocked_count, 1)
        self.assertEqual(interceptor.intercepts[-1]["enforcement_mode"], "hard")

    async def test_inspect_connections_dedupes_same_socket_across_process_tree(self):
        interceptor = MCPInterceptor()
        interceptor._loop = asyncio.get_running_loop()
        interceptor._running = True
        interceptor._schedule_coroutine_threadsafe = Mock(
            side_effect=lambda coro, label: (coro.close(), None)[1]
        )

        connection = {
            "local_endpoint": "10.0.0.10:54000",
            "remote_endpoint": "104.18.3.2:443",
            "local_host": "10.0.0.10",
            "local_port": "54000",
            "remote_host": "104.18.3.2",
            "remote_port": "443",
        }

        with patch.object(
            interceptor,
            "_get_process_args",
            side_effect=["codex", "node helper"],
        ), patch.object(
            interceptor,
            "_inspect_process_network",
            return_value={"established_connections": [connection]},
        ):
            interceptor._inspect_connections_for_pids(root_pid=10, pids={10, 11})

        interceptor._schedule_coroutine_threadsafe.assert_called_once()

    async def test_drain_scheduled_futures_cancels_pending_tasks(self):
        interceptor = MCPInterceptor()
        interceptor._loop = asyncio.get_running_loop()
        interceptor._running = True
        started = asyncio.Event()

        async def sleeper():
            started.set()
            await asyncio.sleep(10)

        future = interceptor._schedule_coroutine_threadsafe(sleeper(), label="test")
        self.assertIsNotNone(future)
        await started.wait()

        await interceptor._drain_scheduled_futures(timeout=0.5)

        self.assertTrue(future.done() or future.cancelled())
        self.assertFalse(interceptor._scheduled_futures)


if __name__ == "__main__":
    unittest.main()
