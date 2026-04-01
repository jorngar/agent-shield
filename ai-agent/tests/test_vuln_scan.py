"""Tests for the vulnerability scanner (vuln_scan.py)."""

import json
import os
import sys
import unittest
from unittest.mock import Mock, patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from vuln_scan import (
    detect_agent_version,
    parse_scan_response,
    scan_agent_vulnerabilities,
    format_scan_result,
)


class DetectAgentVersionTests(unittest.TestCase):
    def test_detects_version_from_stdout(self):
        with patch("subprocess.check_output", return_value="codex v0.2.1\n"):
            result = detect_agent_version("codex", "codex")
        self.assertEqual(result["version"], "0.2.1")
        self.assertIn("codex v0.2.1", result["full_output"])

    def test_detects_semver_variant(self):
        with patch("subprocess.check_output", return_value="my-agent 3.0.0-beta.1\n"):
            result = detect_agent_version("my-agent", "my-agent")
        self.assertEqual(result["version"], "3.0.0-beta.1")

    def test_returns_unknown_on_not_found(self):
        with patch("subprocess.check_output", side_effect=FileNotFoundError):
            result = detect_agent_version("noexist", "noexist")
        self.assertEqual(result["version"], "unknown")

    def test_returns_unknown_on_all_cmds_fail(self):
        with patch(
            "subprocess.check_output",
            side_effect=subprocess.CalledProcessError(1, "cmd"),
        ):
            result = detect_agent_version("noexist", "noexist")
        self.assertEqual(result["version"], "unknown")

    def test_returns_unknown_on_timeout(self):
        import subprocess

        with patch(
            "subprocess.check_output", side_effect=subprocess.TimeoutExpired("cmd", 5)
        ):
            result = detect_agent_version("slow", "slow")
        self.assertEqual(result["version"], "unknown")


class ParseScanResponseTests(unittest.TestCase):
    def test_parse_clean_json(self):
        raw = '{"vulnerable": true, "severity": "high", "findings": [], "recommendation": "update"}'
        parsed = parse_scan_response(raw)
        self.assertTrue(parsed["vulnerable"])
        self.assertEqual(parsed["severity"], "high")
        self.assertFalse(parsed.get("parse_failed", False))

    def test_parse_json_in_fences(self):
        raw = """```json
{"vulnerable": false, "severity": "none", "findings": [], "recommendation": "ok"}
```"""
        parsed = parse_scan_response(raw)
        self.assertFalse(parsed["vulnerable"])
        self.assertFalse(parsed.get("parse_failed", False))

    def test_parse_empty_returns_fallback(self):
        parsed = parse_scan_response("")
        self.assertTrue(parsed.get("parse_failed", False))
        self.assertFalse(parsed["vulnerable"])

    def test_parse_unparseable_returns_fallback(self):
        parsed = parse_scan_response("I have no idea what to say about this")
        self.assertTrue(parsed.get("parse_failed", False))
        self.assertFalse(parsed["vulnerable"])

    def test_parse_with_vulnerability_findings(self):
        raw = json.dumps(
            {
                "vulnerable": True,
                "severity": "critical",
                "findings": [
                    {
                        "cve": "CVE-2026-1234",
                        "title": "RCE in package",
                        "description": "Bad",
                        "source": "https://advisories.example.com",
                    }
                ],
                "recommendation": "Update immediately",
            }
        )
        parsed = parse_scan_response(raw)
        self.assertTrue(parsed["vulnerable"])
        self.assertEqual(parsed["severity"], "critical")
        self.assertEqual(len(parsed["findings"]), 1)
        self.assertEqual(parsed["findings"][0]["cve"], "CVE-2026-1234")


class ScanAgentVulnerabilitiesTests(unittest.TestCase):
    @patch(
        "vuln_scan._query_ollama",
        return_value=json.dumps(
            {
                "vulnerable": False,
                "severity": "none",
                "findings": [],
                "recommendation": "ok",
            }
        ),
    )
    @patch(
        "vuln_scan.detect_agent_version",
        return_value={
            "version": "0.1.0",
            "full_output": "codex v0.1.0",
            "binary_path": "codex",
        },
    )
    def test_scan_returns_result(self, mock_version, mock_ollama):
        result = scan_agent_vulnerabilities("codex", "codex")
        self.assertFalse(result["vulnerable"])
        self.assertEqual(result["version"], "0.1.0")
        self.assertFalse(result["scan_skipped"])

    @patch(
        "vuln_scan.detect_agent_version",
        return_value={
            "version": "unknown",
            "full_output": "",
            "binary_path": "noexist",
        },
    )
    def test_scan_skips_on_unknown_version(self, mock_version):
        result = scan_agent_vulnerabilities("noexist", "noexist")
        self.assertTrue(result["scan_skipped"])
        self.assertEqual(result["scan_reason"], "could_not_detect_version")

    @patch("vuln_scan._query_ollama", return_value=None)
    @patch(
        "vuln_scan.detect_agent_version",
        return_value={
            "version": "1.0.0",
            "full_output": "agent v1.0.0",
            "binary_path": "agent",
        },
    )
    def test_scan_skips_on_ollama_unavailable(self, mock_version, mock_ollama):
        result = scan_agent_vulnerabilities("agent", "agent")
        self.assertTrue(result["scan_skipped"])
        self.assertEqual(result["scan_reason"], "ollama_unavailable")

    @patch(
        "vuln_scan._query_ollama",
        return_value=json.dumps(
            {
                "vulnerable": True,
                "severity": "high",
                "findings": [
                    {
                        "cve": "CVE-2026-9999",
                        "title": "Test vuln",
                        "description": "desc",
                        "source": "src",
                    }
                ],
                "recommendation": "Patch now",
            }
        ),
    )
    @patch(
        "vuln_scan.detect_agent_version",
        return_value={
            "version": "2.0.0",
            "full_output": "agent v2.0.0",
            "binary_path": "agent",
        },
    )
    def test_scan_detects_vulnerabilities(self, mock_version, mock_ollama):
        result = scan_agent_vulnerabilities("agent", "agent")
        self.assertTrue(result["vulnerable"])
        self.assertEqual(result["severity"], "high")
        self.assertEqual(len(result["findings"]), 1)


class FormatScanResultTests(unittest.TestCase):
    def test_format_ok(self):
        result = {
            "agent": "codex",
            "version": "1.0",
            "vulnerable": False,
            "severity": "none",
            "scan_duration_ms": 150,
        }
        text = format_scan_result(result)
        self.assertIn("OK", text)
        self.assertIn("1.0", text)

    def test_format_skipped(self):
        result = {
            "agent": "codex",
            "version": "unknown",
            "binary": "codex",
            "scan_skipped": True,
            "scan_reason": "could_not_detect_version",
        }
        text = format_scan_result(result)
        self.assertIn("Skipped", text)
        self.assertIn("could_not_detect_version", text)

    def test_format_vulnerable(self):
        result = {
            "agent": "codex",
            "version": "1.0",
            "vulnerable": True,
            "severity": "critical",
            "findings": [{"cve": "CVE-2026-1", "title": "RCE"}],
            "recommendation": "Update now",
            "scan_duration_ms": 200,
        }
        text = format_scan_result(result)
        self.assertIn("WARNING", text)
        self.assertIn("CRITICAL", text)
        self.assertIn("CVE-2026-1", text)
        self.assertIn("Update now", text)


# Need this for the CalledProcessError test
import subprocess


if __name__ == "__main__":
    unittest.main()
