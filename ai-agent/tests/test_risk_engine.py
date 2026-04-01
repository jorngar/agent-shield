import os
import sys
import unittest
from unittest.mock import Mock, patch
import requests

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import risk_engine


class ParseRiskResponseTests(unittest.TestCase):
    def test_parse_direct_json(self):
        raw = (
            '{"risk_level":"high","risk_score":82,"category":"mcp_unauthorized",'
            '"summary":"Blocked","recommended_action":"deny","flags":["mcp"]}'
        )
        parsed = risk_engine.parse_risk_response(raw)
        self.assertEqual(parsed["risk_level"], "high")
        self.assertEqual(parsed["risk_score"], 82)

    def test_parse_code_fenced_json(self):
        raw = """```json
        {
          "risk_level": "medium",
          "risk_score": 55,
          "category": "network_access",
          "summary": "Review needed",
          "recommended_action": "review",
          "flags": ["remote"]
        }
        ```"""
        parsed = risk_engine.parse_risk_response(raw)
        self.assertEqual(parsed["risk_level"], "medium")
        self.assertEqual(parsed["recommended_action"], "review")

    def test_parse_invalid_payload_returns_fallback(self):
        parsed = risk_engine.parse_risk_response("not-json")
        self.assertEqual(parsed["flags"], ["parse_error"])
        self.assertEqual(parsed["risk_level"], "medium")


class NormalizeRiskResultTests(unittest.TestCase):
    def test_normalization_clamps_and_uses_score_band(self):
        normalized = risk_engine.normalize_risk_result(
            {
                "risk_level": "INVALID",
                "risk_score": 999,
                "category": "unknown",
                "summary": "",
                "recommended_action": "shipit",
                "flags": "one-flag",
            }
        )
        self.assertEqual(normalized["risk_level"], "critical")
        self.assertEqual(normalized["risk_score"], 100)
        self.assertEqual(normalized["category"], "safe")
        self.assertEqual(normalized["recommended_action"], "deny")
        self.assertIn("one-flag", normalized["flags"])
        self.assertIn("score_level_reconciled", normalized["flags"])
        self.assertIn("risk_level_action_floor", normalized["flags"])

    def test_normalization_applies_action_policy_floor_for_mcp(self):
        normalized = risk_engine.normalize_risk_result(
            {
                "risk_level": "low",
                "risk_score": 10,
                "category": "safe",
                "summary": "looks safe",
                "recommended_action": "approve",
                "flags": [],
            },
            action_type="mcp_connection_attempt",
        )

        self.assertEqual(normalized["risk_level"], "high")
        self.assertEqual(normalized["risk_score"], 76)
        self.assertEqual(normalized["category"], "mcp_unauthorized")
        self.assertEqual(normalized["recommended_action"], "deny")
        self.assertIn("action_policy_score_floor", normalized["flags"])
        self.assertIn("action_policy_level_floor", normalized["flags"])
        self.assertIn("action_policy_category_floor", normalized["flags"])
        self.assertIn("action_policy_action_floor", normalized["flags"])

    def test_normalization_uses_uncertain_default_score_for_unknown_action(self):
        normalized = risk_engine.normalize_risk_result(
            {
                "risk_level": "medium",
                "category": "safe",
                "summary": "missing score",
                "recommended_action": "review",
                "flags": [],
            },
            action_type="unknown_action_type",
        )

        self.assertEqual(normalized["risk_score"], risk_engine.DEFAULT_UNCERTAIN_RISK_SCORE)
        self.assertEqual(normalized["risk_level"], "medium")
        self.assertEqual(normalized["recommended_action"], "review")


class AnalyzeRiskTests(unittest.TestCase):
    def setUp(self):
        risk_engine._risk_cache.clear()

    @patch("risk_engine.requests.post")
    def test_analyze_risk_uses_json_contract(self, mock_post):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "message": {
                "content": (
                    '{"risk_level":"high","risk_score":88,"category":"mcp_unauthorized",'
                    '"summary":"Unauthorized MCP","recommended_action":"deny","flags":["mcp"]}'
                )
            }
        }
        mock_post.return_value = response

        result = risk_engine.analyze_risk(
            agent="codex",
            action_type="mcp_connection_attempt",
            content="127.0.0.1:5000",
            context="test",
        )

        self.assertEqual(mock_post.call_args.kwargs["json"]["format"], "json")
        self.assertEqual(mock_post.call_args.kwargs["json"]["keep_alive"], risk_engine.OLLAMA_KEEP_ALIVE)
        self.assertEqual(result["risk_level"], "critical")
        self.assertEqual(result["recommended_action"], "deny")

    @patch("risk_engine.requests.post")
    def test_analyze_risk_retries_once_on_read_timeout(self, mock_post):
        timeout_error = requests.exceptions.ReadTimeout("read timed out")

        success_response = Mock()
        success_response.raise_for_status.return_value = None
        success_response.json.return_value = {
            "message": {
                "content": (
                    '{"risk_level":"low","risk_score":12,"category":"safe",'
                    '"summary":"Routine local traffic","recommended_action":"approve","flags":[]}'
                )
            }
        }

        mock_post.side_effect = [timeout_error, success_response]

        result = risk_engine.analyze_risk(
            agent="codex",
            action_type="agent_connection_attempt",
            content="127.0.0.1:11434",
            context="warm model retry",
        )

        self.assertEqual(mock_post.call_count, 2)
        first_timeout = mock_post.call_args_list[0].kwargs["timeout"]
        second_timeout = mock_post.call_args_list[1].kwargs["timeout"]
        self.assertGreater(second_timeout[1], first_timeout[1])
        self.assertEqual(result["risk_level"], "medium")
        self.assertEqual(result["recommended_action"], "review")

    @patch("risk_engine.requests.post")
    def test_analyze_risk_truncates_large_content_and_context(self, mock_post):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "message": {
                "content": (
                    '{"risk_level":"medium","risk_score":40,"category":"tool_execution",'
                    '"summary":"Needs review","recommended_action":"review","flags":[]}'
                )
            }
        }
        mock_post.return_value = response

        risk_engine.analyze_risk(
            agent="codex",
            action_type="child_process_spawn",
            content="x" * (risk_engine.OLLAMA_MAX_CONTENT_CHARS + 50),
            context="y" * (risk_engine.OLLAMA_MAX_CONTEXT_CHARS + 50),
        )

        user_message = mock_post.call_args.kwargs["json"]["messages"][1]["content"]
        self.assertIn("...", user_message)
        self.assertLessEqual(len(user_message), 2500)

    @patch("risk_engine.requests.post")
    def test_timeout_fallback_uses_action_specific_baseline(self, mock_post):
        mock_post.side_effect = requests.exceptions.ReadTimeout("read timed out")

        result = risk_engine.analyze_risk(
            agent="codex",
            action_type="destructive_file_operation",
            content="rm -rf ./build",
            context="test",
        )

        self.assertEqual(result["risk_level"], "critical")
        self.assertEqual(result["risk_score"], 95)
        self.assertEqual(result["category"], "destructive_operation")
        self.assertEqual(result["recommended_action"], "deny")
        self.assertIn("timeout", result["flags"])
        self.assertIn("fallback_policy_applied", result["flags"])

    @patch("risk_engine.requests.post")
    def test_parse_error_fallback_uses_action_specific_baseline(self, mock_post):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"message": {"content": "not-json"}}
        mock_post.return_value = response

        result = risk_engine.analyze_risk(
            agent="codex",
            action_type="mcp_connection_attempt",
            content="127.0.0.1:3001",
            context="test",
        )

        self.assertEqual(result["risk_level"], "high")
        self.assertEqual(result["risk_score"], 76)
        self.assertEqual(result["category"], "mcp_unauthorized")
        self.assertEqual(result["recommended_action"], "deny")
        self.assertIn("parse_error", result["flags"])
        self.assertIn("fallback_policy_applied", result["flags"])


if __name__ == "__main__":
    unittest.main()
