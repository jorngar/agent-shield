import hashlib
import json
import threading
import time
import requests
from typing import Dict, Any, Optional
from config import (
    OLLAMA_CONNECT_TIMEOUT,
    OLLAMA_HOST,
    OLLAMA_KEEP_ALIVE,
    OLLAMA_MAX_CONTENT_CHARS,
    OLLAMA_MAX_CONTEXT_CHARS,
    OLLAMA_MODEL,
    OLLAMA_RETRY_COUNT,
    OLLAMA_TIMEOUT,
)

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
destructive_operation : DELETE, DROP, rm -rf, rm, unlink, rmdir, shred, file deletion, irreversible actions
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

Important: Output ONLY the JSON object, no markdown, no explanation. Do NOT think step by step — go straight to the JSON.
/no_think"""


RISK_USER_PROMPT = """/no_think

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
RISK_LEVEL_RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}
RECOMMENDED_ACTION_RANK = {"approve": 0, "review": 1, "deny": 2}

ACTION_POLICY_BASELINES = {
    "destructive_file_operation": {
        "risk_level": "critical",
        "risk_score": 95,
        "category": "destructive_operation",
        "recommended_action": "deny",
        "summary": "Potentially destructive file operation detected. Block immediately unless explicitly approved.",
    },
    "mcp_process_spawn": {
        "risk_level": "high",
        "risk_score": 80,
        "category": "mcp_unauthorized",
        "recommended_action": "deny",
        "summary": "MCP server launch attempt detected. Treat as high risk until reviewed.",
    },
    "mcp_shell_target_access": {
        "risk_level": "high",
        "risk_score": 78,
        "category": "mcp_unauthorized",
        "recommended_action": "deny",
        "summary": "Shell command is targeting an MCP endpoint. Treat as high risk until reviewed.",
    },
    "mcp_connection_attempt": {
        "risk_level": "high",
        "risk_score": 76,
        "category": "mcp_unauthorized",
        "recommended_action": "deny",
        "summary": "MCP connection attempt detected. Treat as high risk until reviewed.",
    },
    "mcp_http_payload": {
        "risk_level": "high",
        "risk_score": 76,
        "category": "mcp_unauthorized",
        "recommended_action": "deny",
        "summary": "MCP proxy payload detected. Treat as high risk until reviewed.",
    },
    "responses_api_connection_attempt": {
        "risk_level": "medium",
        "risk_score": 55,
        "category": "model_api_access",
        "recommended_action": "review",
        "summary": "Remote model API access detected. Review before treating as harmless.",
    },
    "agent_connection_attempt": {
        "risk_level": "medium",
        "risk_score": 48,
        "category": "network_access",
        "recommended_action": "review",
        "summary": "Outbound agent network access detected. Review before treating as harmless.",
    },
    "child_process_spawn": {
        "risk_level": "medium",
        "risk_score": 44,
        "category": "tool_execution",
        "recommended_action": "review",
        "summary": "Child process execution detected. Review before treating as harmless.",
    },
    "shell_process_spawn": {
        "risk_level": "medium",
        "risk_score": 44,
        "category": "tool_execution",
        "recommended_action": "review",
        "summary": "Shell process execution detected. Review before treating as harmless.",
    },
}
DEFAULT_UNCERTAIN_RISK_SCORE = 60
DEFAULT_UNCERTAIN_CATEGORY = "tool_execution"

# --- Risk result cache and Ollama serialization ---
# Ollama can only run one inference at a time on the same model.  When
# multiple intercept threads call analyze_risk concurrently, the later
# requests queue inside Ollama and easily exceed the read timeout.  We
# serialize outbound requests with a lock and cache results so that
# duplicate or near-duplicate actions skip Ollama entirely.
_ollama_lock = threading.Lock()
_risk_cache: Dict[str, Dict[str, Any]] = {}
_CACHE_MAX_SIZE = 256
_CACHE_TTL_SEC = 120.0


def _cache_key(action_type: str, content: str, context: str) -> str:
    raw = f"{action_type}|{content}|{context}"
    return hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()


def _cache_get(key: str) -> Optional[Dict[str, Any]]:
    entry = _risk_cache.get(key)
    if entry is None:
        return None
    if time.time() - entry["_cached_at"] > _CACHE_TTL_SEC:
        _risk_cache.pop(key, None)
        return None
    return {k: v for k, v in entry.items() if k != "_cached_at"}


def _cache_put(key: str, result: Dict[str, Any]) -> None:
    if len(_risk_cache) >= _CACHE_MAX_SIZE:
        oldest_key = min(_risk_cache, key=lambda k: _risk_cache[k].get("_cached_at", 0))
        _risk_cache.pop(oldest_key, None)
    _risk_cache[key] = {**result, "_cached_at": time.time()}


def _risk_level_from_score(score: int) -> str:
    if score >= 86:
        return "critical"
    if score >= 61:
        return "high"
    if score >= 26:
        return "medium"
    return "low"


def _minimum_recommended_action_for_level(risk_level: str) -> str:
    if risk_level in {"high", "critical"}:
        return "deny"
    if risk_level == "medium":
        return "review"
    return "approve"


def _action_policy_baseline(action_type: str) -> Dict[str, Any]:
    return ACTION_POLICY_BASELINES.get(action_type, {})


def _build_fallback_summary(action_type: str, failure_kind: str) -> str:
    baseline = _action_policy_baseline(action_type)
    risk_level = baseline.get("risk_level", "medium")
    action_summary = baseline.get("summary", "Sensitive action detected.")

    failure_prefix = {
        "timeout": "Local risk model timed out while reviewing this action.",
        "service_unavailable": "Local risk model was unavailable while reviewing this action.",
        "invalid_service_response": "Local risk model returned an invalid response while reviewing this action.",
        "parse_error": "Local risk model returned an unreadable assessment for this action.",
    }.get(failure_kind, "Local risk model could not complete this review.")

    guidance = {
        "low": "Treat it as routine but continue monitoring.",
        "medium": "Escalate it for review before treating it as harmless.",
        "high": "Treat it as dangerous until it is explicitly reviewed.",
        "critical": "Block it immediately unless explicitly approved.",
    }[risk_level]

    return f"{failure_prefix} {action_summary} {guidance}"


def _fallback_response(
    action_type: str, failure_kind: str, latency_ms: int, detail: Optional[str] = None
) -> Dict[str, Any]:
    baseline = _action_policy_baseline(action_type)
    risk_level = baseline.get("risk_level", "medium")
    risk_score = int(baseline.get("risk_score", DEFAULT_UNCERTAIN_RISK_SCORE))
    category = baseline.get("category", DEFAULT_UNCERTAIN_CATEGORY)
    recommended_action = baseline.get(
        "recommended_action", _minimum_recommended_action_for_level(risk_level)
    )
    summary = _build_fallback_summary(action_type, failure_kind)
    if detail and failure_kind == "service_unavailable":
        summary = f"{summary} ({detail})"
    return {
        "risk_level": risk_level,
        "risk_score": risk_score,
        "category": category,
        "summary": summary,
        "recommended_action": recommended_action,
        "flags": [failure_kind, "fallback_policy_applied"],
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


def _truncate_text(value: str, limit: int) -> str:
    text = str(value or "")
    if len(text) <= limit:
        return text
    if limit <= 3:
        return text[:limit]
    return text[: limit - 3] + "..."


def _build_request_payload(user_message: str, max_tokens: int) -> Dict[str, Any]:
    return {
        "model": OLLAMA_MODEL,
        "format": "json",
        "messages": [
            {"role": "system", "content": RISK_SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        "stream": False,
        "keep_alive": OLLAMA_KEEP_ALIVE,
        "options": {
            "temperature": 0.1,
            "num_predict": max_tokens,
            "top_k": 20,
            "top_p": 0.95,
        },
    }


def _post_ollama_chat(user_message: str) -> requests.Response:
    last_error: Optional[Exception] = None
    read_timeout = OLLAMA_TIMEOUT

    for attempt in range(OLLAMA_RETRY_COUNT + 1):
        max_tokens = 1024 if attempt == 0 else 512
        payload = _build_request_payload(
            user_message=user_message, max_tokens=max_tokens
        )
        try:
            response = requests.post(
                f"{OLLAMA_HOST}/api/chat",
                json=payload,
                timeout=(OLLAMA_CONNECT_TIMEOUT, read_timeout),
            )
            response.raise_for_status()
            return response
        except requests.exceptions.ReadTimeout as error:
            last_error = error
            if attempt >= OLLAMA_RETRY_COUNT:
                break
            read_timeout = max(read_timeout + 30.0, read_timeout * 1.5)
        except requests.exceptions.RequestException as error:
            raise error

    if last_error is not None:
        raise last_error
    raise requests.exceptions.RequestException("Unknown Ollama request failure")


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


def normalize_risk_result(
    payload: Dict[str, Any], action_type: str = ""
) -> Dict[str, Any]:
    baseline = _action_policy_baseline(action_type)
    default_score = int(baseline.get("risk_score", DEFAULT_UNCERTAIN_RISK_SCORE))
    default_category = baseline.get("category", "safe")
    default_action = baseline.get("recommended_action", "review")

    risk_level = str(payload.get("risk_level", "medium")).lower()
    if risk_level not in VALID_RISK_LEVELS:
        risk_level = "medium"

    try:
        risk_score = int(payload.get("risk_score", default_score))
    except (TypeError, ValueError):
        risk_score = default_score
    risk_score = max(0, min(100, risk_score))

    category = str(payload.get("category", default_category)).lower()
    if category not in VALID_CATEGORIES:
        category = default_category

    summary = str(payload.get("summary", "")).strip() or "Risk assessment completed."

    recommended_action = str(payload.get("recommended_action", default_action)).lower()
    if recommended_action not in VALID_RECOMMENDED_ACTIONS:
        recommended_action = default_action

    flags = payload.get("flags", [])
    if not isinstance(flags, list):
        flags = [str(flags)]
    flags = [str(flag) for flag in flags if str(flag).strip()]

    derived_risk_level = _risk_level_from_score(risk_score)
    if RISK_LEVEL_RANK[derived_risk_level] > RISK_LEVEL_RANK[risk_level]:
        risk_level = derived_risk_level
        if "score_level_reconciled" not in flags:
            flags.append("score_level_reconciled")

    if baseline:
        baseline_score = int(baseline["risk_score"])
        baseline_level = baseline["risk_level"]
        baseline_action = baseline["recommended_action"]
        baseline_category = baseline["category"]

        if risk_score < baseline_score:
            risk_score = baseline_score
            if "action_policy_score_floor" not in flags:
                flags.append("action_policy_score_floor")

        if RISK_LEVEL_RANK[baseline_level] > RISK_LEVEL_RANK[risk_level]:
            risk_level = baseline_level
            if "action_policy_level_floor" not in flags:
                flags.append("action_policy_level_floor")

        if baseline_category != "safe" and (
            category == "safe" or risk_level in {"high", "critical"}
        ):
            category = baseline_category
            if "action_policy_category_floor" not in flags:
                flags.append("action_policy_category_floor")

        if (
            RECOMMENDED_ACTION_RANK.get(recommended_action, 1)
            < RECOMMENDED_ACTION_RANK[baseline_action]
        ):
            recommended_action = baseline_action
            if "action_policy_action_floor" not in flags:
                flags.append("action_policy_action_floor")

    minimum_action = _minimum_recommended_action_for_level(risk_level)
    if (
        RECOMMENDED_ACTION_RANK.get(recommended_action, 1)
        < RECOMMENDED_ACTION_RANK[minimum_action]
    ):
        recommended_action = minimum_action
        if "risk_level_action_floor" not in flags:
            flags.append("risk_level_action_floor")

    return {
        "risk_level": risk_level,
        "risk_score": risk_score,
        "category": category,
        "summary": summary,
        "recommended_action": recommended_action,
        "flags": flags,
    }


def analyze_risk(agent: str, action_type: str, content: str, context: str = "") -> dict:
    trimmed_content = _truncate_text(content, OLLAMA_MAX_CONTENT_CHARS)
    ctx = _truncate_text(context or "none", OLLAMA_MAX_CONTEXT_CHARS)

    # Check cache first — avoids hitting Ollama for repeated/similar actions.
    key = _cache_key(action_type, trimmed_content, ctx)
    cached = _cache_get(key)
    if cached is not None:
        cached["latency_ms"] = 0
        if "cache_hit" not in cached.get("flags", []):
            cached.setdefault("flags", []).append("cache_hit")
        return cached

    user_message = RISK_USER_PROMPT.format(
        agent=agent, action_type=action_type, content=trimmed_content, context=ctx
    )

    start = time.time()

    # Serialize Ollama requests — the model can only run one inference at
    # a time, so concurrent requests just queue inside Ollama and cause
    # the later ones to time out.  The lock ensures we don't pile up.
    with _ollama_lock:
        # Re-check cache after acquiring lock — another thread may have
        # just populated it for the same action while we waited.
        cached = _cache_get(key)
        if cached is not None:
            cached["latency_ms"] = 0
            if "cache_hit" not in cached.get("flags", []):
                cached.setdefault("flags", []).append("cache_hit")
            return cached

        try:
            response = _post_ollama_chat(user_message)
        except requests.exceptions.ReadTimeout as e:
            return _fallback_response(
                action_type=action_type,
                failure_kind="timeout",
                latency_ms=int((time.time() - start) * 1000),
            )
        except requests.exceptions.RequestException as e:
            return _fallback_response(
                action_type=action_type,
                failure_kind="service_unavailable",
                latency_ms=int((time.time() - start) * 1000),
                detail=str(e),
            )

    latency_ms = int((time.time() - start) * 1000)
    try:
        payload = response.json()
    except ValueError:
        return _fallback_response(
            action_type=action_type,
            failure_kind="invalid_service_response",
            latency_ms=latency_ms,
        )

    message = payload.get("message", {})
    raw = str(message.get("content", "")).strip()

    # Qwen 3.x sometimes puts all output in the "thinking" field and
    # leaves "content" empty.  Try to extract usable JSON from either.
    thinking_raw = str(message.get("thinking", "")).strip()
    if not raw and thinking_raw:
        raw = thinking_raw

    parsed = parse_risk_response(raw)

    # If the primary source failed to parse and there was a separate
    # thinking field, try extracting JSON from that too.
    if parsed.get("flags") == ["parse_error"] and thinking_raw and thinking_raw != raw:
        thinking_parsed = parse_risk_response(thinking_raw)
        if thinking_parsed.get("flags") != ["parse_error"]:
            parsed = thinking_parsed

    if parsed.get("flags") == ["parse_error"]:
        return _fallback_response(
            action_type=action_type,
            failure_kind="parse_error",
            latency_ms=latency_ms,
        )

    result = normalize_risk_result(parsed, action_type=action_type)
    result["latency_ms"] = latency_ms

    # Flag when the model hit its token limit before completing the
    # response — the JSON may be truncated or absent.
    if payload.get("done_reason") == "length":
        if result.get("flags") is None:
            result["flags"] = []
        if "truncated_response" not in result["flags"]:
            result["flags"].append("truncated_response")

    # Cache successful results (not fallbacks).
    if "service_unavailable" not in result.get("flags", []):
        _cache_put(key, result)

    return result


def check_ollama_health() -> Dict[str, Any]:
    """Check if Ollama is reachable and the configured model is available.

    Returns a dict with ``ok``, ``host``, ``model``, ``model_loaded``, and
    ``latency_ms`` keys.  On failure ``ok`` is False and ``error`` is set.
    """
    start = time.time()
    info: Dict[str, Any] = {
        "ok": False,
        "host": OLLAMA_HOST,
        "model": OLLAMA_MODEL,
    }

    # 1. Is the daemon reachable?
    try:
        resp = requests.get(
            f"{OLLAMA_HOST}/api/tags",
            timeout=(OLLAMA_CONNECT_TIMEOUT, 5.0),
        )
        resp.raise_for_status()
    except requests.exceptions.ConnectionError:
        info["error"] = (
            f"Cannot connect to Ollama at {OLLAMA_HOST}. "
            "Is the Ollama daemon running?  Start it with: ollama serve"
        )
        info["latency_ms"] = int((time.time() - start) * 1000)
        return info
    except requests.exceptions.ReadTimeout:
        info["error"] = f"Ollama at {OLLAMA_HOST} timed out on /api/tags."
        info["latency_ms"] = int((time.time() - start) * 1000)
        return info
    except requests.exceptions.RequestException as exc:
        info["error"] = f"Ollama health check failed: {exc}"
        info["latency_ms"] = int((time.time() - start) * 1000)
        return info

    # 2. Is the model pulled?
    try:
        tags = resp.json()
        available_models = {
            m.get("name", "").split(":")[0] for m in tags.get("models", [])
        }
        model_base = OLLAMA_MODEL.split(":")[0]
        info["model_loaded"] = model_base in available_models
    except (ValueError, AttributeError):
        info["model_loaded"] = None

    # 3. Pre-warm the model (send a trivial prompt so Ollama loads weights).
    try:
        warm_resp = requests.post(
            f"{OLLAMA_HOST}/api/generate",
            json={
                "model": OLLAMA_MODEL,
                "prompt": "ok",
                "stream": False,
                "options": {"num_predict": 1},
            },
            timeout=(OLLAMA_CONNECT_TIMEOUT, min(15.0, OLLAMA_TIMEOUT)),
        )
        warm_resp.raise_for_status()
        info["model_warmed"] = True
    except requests.exceptions.RequestException:
        info["model_warmed"] = False

    info["ok"] = True
    info["latency_ms"] = int((time.time() - start) * 1000)
    return info


def check_ollama_health_sync() -> Dict[str, Any]:
    """Synchronous wrapper around :func:`check_ollama_health`."""
    return check_ollama_health()
