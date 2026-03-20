import os
import sys
import unittest
from unittest.mock import Mock, patch

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
    def test_normalization_clamps_and_defaults(self):
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
        self.assertEqual(normalized["risk_level"], "medium")
        self.assertEqual(normalized["risk_score"], 100)
        self.assertEqual(normalized["category"], "safe")
        self.assertEqual(normalized["recommended_action"], "review")
        self.assertEqual(normalized["flags"], ["one-flag"])


class AnalyzeRiskTests(unittest.TestCase):
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
        self.assertEqual(result["risk_level"], "high")
        self.assertEqual(result["recommended_action"], "deny")


if __name__ == "__main__":
    unittest.main()
