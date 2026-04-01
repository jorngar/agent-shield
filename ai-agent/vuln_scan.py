"""Startup vulnerability scan for agent dependencies.

Checks the version of the target agent binary against known vulnerability
advisories using an Ollama-hosted LLM query.  The scan runs once at startup
and emits warnings — it never blocks the agent launch.

The scan is best-effort: if Ollama is unavailable or the agent version
cannot be detected, the scan is skipped with a log message.
"""

import json
import subprocess
import re
import time
from typing import Any, Dict, List, Optional

from config import (
    OLLAMA_CONNECT_TIMEOUT,
    OLLAMA_HOST,
    OLLAMA_MODEL,
    OLLAMA_TIMEOUT,
)

# Common CVE databases / advisory URLs the LLM should reference.
_ADVISORY_SOURCES = [
    "https://github.com/advisories",
    "https://cve.mitre.org",
    "https://osv.dev",
]

_SCAN_PROMPT_TEMPLATE = """\
You are a security advisor.  Given the following AI agent and version, check \
whether there are any **known CVEs, critical vulnerabilities, or supply-chain \
compromises** as of April 2026.

Agent: {agent_name}
Version: {agent_version}
Binary: {binary_path}

Consider:
- Known CVEs for the agent package itself
- Compromised npm/PyPI packages in its dependency tree
- Typosquatting or fake packages with similar names
- Malicious postinstall scripts reported in advisories
- Supply-chain attacks on the agent's ecosystem (npm, PyPI, etc.)

Respond ONLY with JSON (no markdown fences) using this schema:
{{
  "vulnerable": true/false,
  "severity": "none"|"low"|"medium"|"high"|"critical",
  "findings": [
    {{
      "cve": "CVE-YYYY-XXXXX or N/A",
      "title": "Short title",
      "description": "One-sentence description",
      "source": "URL or source name"
    }}
  ],
  "recommendation": "One-sentence recommendation or 'No action needed'"
}}

If you are unsure or have no data, set "vulnerable": false and "severity": "none".
Do NOT hallucinate CVE numbers.
"""

# Maximum number of characters the LLM response can be.
_MAX_RESPONSE_CHARS = 2000


def detect_agent_version(agent_name: str, binary: str) -> Dict[str, str]:
    """Attempt to detect the version of an agent binary.

    Returns a dict with ``version``, ``full_output``, and ``binary_path``.
    If detection fails, ``version`` is ``"unknown"``.
    """
    result: Dict[str, str] = {
        "version": "unknown",
        "full_output": "",
        "binary_path": binary,
    }

    version_cmds = [
        [binary, "--version"],
        [binary, "-v"],
        [binary, "version"],
        [binary, "--help"],
    ]

    for cmd in version_cmds:
        try:
            out = subprocess.check_output(
                cmd, text=True, stderr=subprocess.DEVNULL, timeout=5
            ).strip()
            if out:
                result["full_output"] = out[:500]
                # Try to extract a version-like string
                match = re.search(r"(\d+\.\d+(?:\.\d+)?(?:[-\w.]*))", out)
                if match:
                    result["version"] = match.group(1)
                else:
                    result["version"] = out.splitlines()[0][:80]
                return result
        except (
            FileNotFoundError,
            subprocess.CalledProcessError,
            subprocess.TimeoutExpired,
        ):
            continue

    return result


def _query_ollama(prompt: str) -> Optional[str]:
    """Send a prompt to Ollama and return the response text."""
    import requests

    payload = {
        "model": OLLAMA_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {
            "temperature": 0.1,
            "num_predict": 512,
        },
    }

    try:
        response = requests.post(
            f"{OLLAMA_HOST}/api/chat",
            json=payload,
            timeout=(OLLAMA_CONNECT_TIMEOUT, OLLAMA_TIMEOUT),
        )
        response.raise_for_status()
        data = response.json()
        return data.get("message", {}).get("content", "")
    except Exception:
        return None


def parse_scan_response(raw: str) -> Dict[str, Any]:
    """Parse the LLM response into a structured scan result."""
    fallback: Dict[str, Any] = {
        "vulnerable": False,
        "severity": "unknown",
        "findings": [],
        "recommendation": "Could not parse scan response; manual review suggested.",
        "parse_failed": True,
    }

    if not raw:
        return fallback

    # Try to extract JSON from the raw response
    candidates = []
    stripped = raw.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        candidates.append(stripped)

    # Look for JSON in code fences
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if fence_match:
        candidates.append(fence_match.group(1).strip())

    # Look for anything that looks like a JSON object
    json_match = re.search(r"\{[^{}]*\"vulnerable\"[^{}]*\}", raw, re.DOTALL)
    if json_match:
        candidates.append(json_match.group(0))

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict) and "vulnerable" in parsed:
                parsed["parse_failed"] = False
                return parsed
        except json.JSONDecodeError:
            continue

    return fallback


def scan_agent_vulnerabilities(
    agent_name: str,
    binary: str,
    logger=None,
) -> Dict[str, Any]:
    """Run a vulnerability scan for an agent.

    Returns a scan result dict.  Never raises — all errors are caught and
    returned as a non-vulnerable result with ``scan_skipped`` set.
    """
    from config import OLLAMA_MODEL

    scan_start = time.time()
    result: Dict[str, Any] = {
        "agent": agent_name,
        "binary": binary,
        "version": "unknown",
        "vulnerable": False,
        "severity": "none",
        "findings": [],
        "recommendation": "",
        "scan_duration_ms": 0,
        "scan_skipped": False,
        "scan_reason": "",
    }

    # 1. Detect version
    version_info = detect_agent_version(agent_name, binary)
    result["version"] = version_info["version"]
    result["binary_path"] = version_info["binary_path"]

    if version_info["version"] == "unknown":
        result["scan_skipped"] = True
        result["scan_reason"] = "could_not_detect_version"
        result["scan_duration_ms"] = int((time.time() - scan_start) * 1000)
        if logger:
            logger(
                f"[VulnScan] Skipped: could not detect version of {binary}",
                level="WARNING",
            )
        return result

    # 2. Query Ollama
    prompt = _SCAN_PROMPT_TEMPLATE.format(
        agent_name=agent_name,
        agent_version=version_info["version"],
        binary_path=version_info["binary_path"],
    )

    raw_response = _query_ollama(prompt)
    if raw_response is None:
        result["scan_skipped"] = True
        result["scan_reason"] = "ollama_unavailable"
        result["scan_duration_ms"] = int((time.time() - scan_start) * 1000)
        if logger:
            logger(
                "[VulnScan] Skipped: Ollama unavailable for vulnerability query",
                level="WARNING",
            )
        return result

    # 3. Parse response
    parsed = parse_scan_response(raw_response[:_MAX_RESPONSE_CHARS])
    result["vulnerable"] = parsed.get("vulnerable", False)
    result["severity"] = parsed.get("severity", "unknown")
    result["findings"] = parsed.get("findings", [])
    result["recommendation"] = parsed.get("recommendation", "")
    result["scan_duration_ms"] = int((time.time() - scan_start) * 1000)

    return result


def format_scan_result(result: Dict[str, Any]) -> str:
    """Format a scan result as a human-readable string."""
    if result.get("scan_skipped"):
        reason = result.get("scan_reason", "unknown")
        return f"[VulnScan] Skipped ({reason}): {result['binary']} v{result['version']}"

    version = result.get("version", "unknown")
    agent = result.get("agent", "unknown")
    severity = result.get("severity", "none")
    vulnerable = result.get("vulnerable", False)
    duration = result.get("scan_duration_ms", 0)

    if not vulnerable or severity == "none":
        return f"[VulnScan] OK: {agent} v{version} — no known vulnerabilities ({duration}ms)"

    findings = result.get("findings", [])
    lines = [
        f"[VulnScan] WARNING: {agent} v{version} — {severity.upper()} vulnerabilities detected ({duration}ms)",
    ]
    for f in findings[:3]:
        cve = f.get("cve", "N/A")
        title = f.get("title", "Unknown")
        lines.append(f"  - {cve}: {title}")

    rec = result.get("recommendation", "")
    if rec:
        lines.append(f"  Recommendation: {rec}")

    return "\n".join(lines)
