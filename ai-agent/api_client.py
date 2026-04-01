import httpx
import asyncio
import json
from typing import Dict, Any
from config import BACKEND_URL


class BackendClient:
    """Client for the Node Express backend API."""

    def __init__(self, base_url: str = BACKEND_URL):
        self.base_url = (base_url or BACKEND_URL).rstrip("/")
        self.timeout = 5.0
        self.debug_hook = None

    def _api_url(self, path: str) -> str:
        clean_path = "/" + path.lstrip("/")
        if self.base_url.endswith("/api"):
            return f"{self.base_url}{clean_path}"
        return f"{self.base_url}/api{clean_path}"

    def _debug(self, message: str) -> None:
        if callable(self.debug_hook):
            self.debug_hook(message)

    @staticmethod
    def _truncate_payload_for_log(payload: Any, max_len: int = 500) -> str:
        try:
            text = json.dumps(payload, default=str)
        except (TypeError, ValueError):
            text = str(payload)
        if len(text) > max_len:
            return text[:max_len] + "...(truncated)"
        return text

    async def health_check(self) -> Dict[str, Any]:
        async with httpx.AsyncClient() as client:
            try:
                request_url = self._api_url("/health")
                self._debug(f"GET {request_url} (health check) start")
                response = await client.get(
                    request_url,
                    timeout=self.timeout,
                )
                self._debug(
                    f"GET {request_url} (health check) -> {response.status_code}"
                )
                if response.is_error:
                    return {
                        "ok": False,
                        "http_status": response.status_code,
                        "error": response.text[:300],
                    }
                data = response.json()
                return {"ok": True, "status": data.get("status", "ok")}
            except (httpx.HTTPError, ValueError) as e:
                return {"ok": False, "error": str(e)}

    async def submit_intercept(
        self,
        session_id: str,
        agent: str,
        action_type: str,
        content: str,
        risk: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Submit an action for approval.

        Body:
        {
          "session_id": "<uuid>",
          "agent": "codex",
          "action_type": "mcp_server",
          "content": "<the code or command being executed>",
          "risk": {
            "risk_level": "high",
            "risk_score": 78,
            "category": "mcp_unauthorized",
            "summary": "Agent is attempting to connect to unauthorized MCP server.",
            "recommended_action": "deny",
            "flags": ["filesystem_mcp", "unauthorized_access"]
          }
        }

        Response:
        {
          "intercept_id": "<uuid>",
          "status": "pending"
        }
        """
        async with httpx.AsyncClient() as client:
            payload = {
                "session_id": session_id,
                "agent": agent,
                "action_type": action_type,
                "content": content,
                "risk": risk,
            }
            request_url = self._api_url("/intercept")
            try:
                self._debug(
                    f"POST {request_url} submit_intercept start "
                    f"action_type={action_type}; "
                    f"session_id={session_id}; "
                    f"risk_level={risk.get('risk_level')}; "
                    f"risk_score={risk.get('risk_score')}; "
                    f"payload={self._truncate_payload_for_log(payload)}"
                )
                response = await client.post(
                    request_url,
                    json=payload,
                    timeout=self.timeout,
                )
                response_preview = response.text[:500] if response.text else "(empty)"
                self._debug(
                    f"POST {request_url} submit_intercept -> "
                    f"status={response.status_code}; "
                    f"body={response_preview}"
                )
                if response.is_error:
                    return {
                        "intercept_id": None,
                        "status": "error",
                        "http_status": response.status_code,
                        "error": response.text[:300],
                        "request_url": request_url,
                    }
                result = response.json()
                result["request_url"] = request_url
                return result
            except httpx.HTTPError as e:
                error_message = f"{type(e).__name__}: {e}".strip(": ")
                self._debug(
                    f"POST {request_url} submit_intercept error {error_message}"
                )
                return {
                    "intercept_id": None,
                    "status": "error",
                    "error": error_message,
                    "request_url": request_url,
                }

    async def poll_decision(
        self, intercept_id: str, max_attempts: int = 60, poll_interval: float = 0.5
    ) -> Dict[str, Any]:
        """
        Poll for decision on an intercept.

        Response when decided:
        {
          "intercept_id": "<uuid>",
          "decision": "approve" | "deny"
        }
        """
        async with httpx.AsyncClient() as client:
            for _ in range(max_attempts):
                await asyncio.sleep(poll_interval)
                request_url = self._api_url(f"/intercept/{intercept_id}")
                try:
                    self._debug(
                        f"GET {request_url} poll_decision start intercept_id={intercept_id}"
                    )
                    response = await client.get(
                        request_url,
                        timeout=self.timeout,
                    )
                    response_preview = response.text[:300] if response.text else "(empty)"
                    self._debug(
                        f"GET {request_url} poll_decision -> "
                        f"status={response.status_code}; body={response_preview}"
                    )
                    if response.is_error:
                        continue
                    data = response.json()
                    data["request_url"] = request_url
                    if data.get("decision") in ("approve", "deny"):
                        self._debug(
                            f"GET {request_url} poll_decision resolved: "
                            f"decision={data['decision']}; intercept_id={intercept_id}"
                        )
                        return data
                except (httpx.HTTPError, ValueError) as exc:
                    self._debug(
                        f"GET {request_url} poll_decision error: {exc}"
                    )
                    continue

            self._debug(
                f"poll_decision timed out after {max_attempts} attempts for intercept_id={intercept_id}"
            )
            return {"intercept_id": intercept_id, "decision": "deny", "timeout": True}

    async def report_session_result(
        self, session_id: str, status: str, intercepts: list
    ) -> Dict[str, Any]:
        """
        Report session result to backend.

        Body:
        {
          "session_id": "<uuid>",
          "status": "success" | "failed" | "blocked",
          "intercepts": [
            {
              "intercept_id": "<uuid>",
              "decision": "deny",
              "risk_level": "high"
            }
          ]
        }
        """
        async with httpx.AsyncClient() as client:
            try:
                request_url = self._api_url("/session/result")
                report_payload = {
                    "session_id": session_id,
                    "status": status,
                    "intercepts": intercepts,
                }
                self._debug(
                    f"POST {request_url} report_session_result start "
                    f"status={status}; "
                    f"intercept_count={len(intercepts)}; "
                    f"payload={self._truncate_payload_for_log(report_payload)}"
                )
                response = await client.post(
                    request_url,
                    json=report_payload,
                    timeout=self.timeout,
                )
                response_preview = response.text[:500] if response.text else "(empty)"
                self._debug(
                    f"POST {request_url} report_session_result -> "
                    f"status={response.status_code}; body={response_preview}"
                )
                if response.is_error:
                    return {
                        "error": response.text[:300],
                        "http_status": response.status_code,
                        "request_url": request_url,
                    }
                result = response.json()
                result["request_url"] = request_url
                return result
            except httpx.HTTPError as e:
                error_message = f"{type(e).__name__}: {e}".strip(": ")
                self._debug(
                    f"POST {request_url} report_session_result error {error_message}"
                )
                return {"error": error_message}


def create_backend_client() -> BackendClient:
    return BackendClient()
