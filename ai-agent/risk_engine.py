import json
import time
import requests
from typing import Dict, Any
from config import OLLAMA_HOST, OLLAMA_MODEL

RISK_SYSTEM_PROMPT = """You are a security risk analysis engine for AI agents. Your role is to evaluate agent actions across the full agent process tree for potential security threats, including MCP usage, child-process execution, browser tooling, package bootstraps, and outbound model API calls.

<objectives>
1. Analyze the action described in <agent_action> tags.
2. Identify all security risks, especially risky child processes, external network access, MCP server connections, and model API access.
3. Return your assessment as a single valid JSON object.
</objectives>

<risk_levels>
- low      (score 0-25):  safe, routine operation
- medium   (score 26-60): sensitive, needs human review  
- high     (score 61-85): dangerous, recommend deny
- critical (score 86-100): must deny immediately
</risk_levels>

<categories>
credential_leak       : API keys, passwords, tokens exposed
destructive_operation : DELETE, DROP, rm -rf, irreversible actions
data_exfiltration     : sending data to external destinations
privilege_escalation  : sudo, system file modification
network_access        : outbound HTTP to external URLs
model_api_access      : outbound connection to remote LLM / Responses API
mcp_unauthorized      : unauthorized MCP server connection attempt
file_system_write     : writing outside working directory
dependency_injection  : installing packages, modifying deps
tool_execution        : shell/tool/process execution with unclear or risky intent
browser_automation    : browser automation that can navigate or act on remote sites
safe                  : no risk detected
</categories>

<output_schema>
{
  "risk_level": "<low|medium|high|critical>",
  "risk_score": <integer 0-100>,
  "category": "<category>",
  "summary": "<1-2 plain English sentences for a non-technical manager>",
  "recommended_action": "<approve|review|deny>",
  "flags": ["<flag>"]
}
</output_schema>

Important: Output ONLY the JSON object, no markdown, no explanation."""


RISK_USER_PROMPT = """<no_think>

<agent_action>
  <agent>{agent}</agent>
  <action_type>{action_type}</action_type>
  <content>{content}</content>
  <context>{context}</context>
</agent_action>

<objectives>
1. Identify all security risks in the action above, especially risky process execution, outbound model/API access, and MCP server usage.
2. Return your assessment as a single valid JSON object and nothing else.
</objectives>

<output_schema>
{{
  "risk_level": "<low|medium|high|critical>",
  "risk_score": <integer 0-100>,
  "category": "<category>",
  "summary": "<1-2 plain English sentences>",
  "recommended_action": "<approve|review|deny>",
  "flags": ["<flag>"]
}}
</output_schema>"""


VALID_RISK_LEVELS = {"low", "medium", "high", "critical"}
VALID_CATEGORIES = {
    "credential_leak",
    "destructive_operation",
    "data_exfiltration",
    "privilege_escalation",
    "network_access",
    "model_api_access",
    "mcp_unauthorized",
    "file_system_write",
    "dependency_injection",
    "tool_execution",
    "browser_automation",
    "safe",
}
VALID_RECOMMENDED_ACTIONS = {"approve", "review", "deny"}


def _fallback_response(summary: str, flag: str, latency_ms: int) -> Dict[str, Any]:
    return {
        "risk_level": "medium",
        "risk_score": 50,
        "category": "safe",
        "summary": summary,
        "recommended_action": "review",
        "flags": [flag],
        "latency_ms": latency_ms,
    }


def _extract_json_snippet(raw: str) -> str:
    text = raw.strip()
    if not text:
        return ""

    if text.startswith("```"):
        parts = text.split("```")
        if len(parts) > 1:
            text = parts[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()

    first = text.find("{")
    last = text.rfind("}")
    if first != -1 and last != -1 and first < last:
        return text[first : last + 1]

    return text


def parse_risk_response(raw: str) -> Dict[str, Any]:
    candidates = []
    snippet = _extract_json_snippet(raw)
    if snippet:
        candidates.append(snippet)
    candidates.append(raw.strip())
    candidates.extend(line.strip() for line in raw.splitlines() if line.strip())

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            continue

    return {
        "risk_level": "medium",
        "risk_score": 50,
        "category": "safe",
        "summary": "Failed to parse risk analysis response",
        "recommended_action": "review",
        "flags": ["parse_error"],
    }


def normalize_risk_result(payload: Dict[str, Any]) -> Dict[str, Any]:
    risk_level = str(payload.get("risk_level", "medium")).lower()
    if risk_level not in VALID_RISK_LEVELS:
        risk_level = "medium"

    try:
        risk_score = int(payload.get("risk_score", 50))
    except (TypeError, ValueError):
        risk_score = 50
    risk_score = max(0, min(100, risk_score))

    category = str(payload.get("category", "safe")).lower()
    if category not in VALID_CATEGORIES:
        category = "safe"

    summary = str(payload.get("summary", "")).strip() or "Risk assessment completed."

    recommended_action = str(payload.get("recommended_action", "review")).lower()
    if recommended_action not in VALID_RECOMMENDED_ACTIONS:
        recommended_action = "review"

    flags = payload.get("flags", [])
    if not isinstance(flags, list):
        flags = [str(flags)]
    flags = [str(flag) for flag in flags if str(flag).strip()]

    return {
        "risk_level": risk_level,
        "risk_score": risk_score,
        "category": category,
        "summary": summary,
        "recommended_action": recommended_action,
        "flags": flags,
    }


def analyze_risk(agent: str, action_type: str, content: str, context: str = "") -> dict:
    user_message = RISK_USER_PROMPT.format(
        agent=agent, action_type=action_type, content=content, context=context or "none"
    )

    start = time.time()

    try:
        response = requests.post(
            f"{OLLAMA_HOST}/api/chat",
            json={
                "model": OLLAMA_MODEL,
                "format": "json",
                "messages": [
                    {"role": "system", "content": RISK_SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                "stream": False,
                "options": {
                    "temperature": 0.1,
                    "num_predict": 512,
                    "top_k": 20,
                    "top_p": 0.95,
                },
            },
            timeout=30,
        )
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        return _fallback_response(
            summary=f"Risk analysis service unavailable: {str(e)}",
            flag="service_unavailable",
            latency_ms=int((time.time() - start) * 1000),
        )

    latency_ms = int((time.time() - start) * 1000)
    try:
        payload = response.json()
    except ValueError:
        return _fallback_response(
            summary="Risk analysis service returned invalid JSON",
            flag="invalid_service_response",
            latency_ms=latency_ms,
        )

    message = payload.get("message", {})
    raw = str(message.get("content", "")).strip()
    if not raw:
        raw = str(message.get("thinking", "")).strip()

    parsed = parse_risk_response(raw)
    result = normalize_risk_result(parsed)
    result["latency_ms"] = latency_ms
    return result
