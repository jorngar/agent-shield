import httpx
import asyncio
from typing import Dict, Any
from config import BACKEND_URL


class BackendClient:
    """Client for the Node Express backend API."""

    def __init__(self, base_url: str = BACKEND_URL):
        self.base_url = (base_url or BACKEND_URL).rstrip("/")
        self.timeout = 5.0

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
            try:
                response = await client.post(
                    f"{self.base_url}/api/intercept",
                    json={
                        "session_id": session_id,
                        "agent": agent,
                        "action_type": action_type,
                        "content": content,
                        "risk": risk,
                    },
                    timeout=self.timeout,
                )
                if response.is_error:
                    return {
                        "intercept_id": None,
                        "status": "error",
                        "http_status": response.status_code,
                        "error": response.text[:300],
                    }
                return response.json()
            except httpx.HTTPError as e:
                return {"intercept_id": None, "status": "error", "error": str(e)}

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
                try:
                    response = await client.get(
                        f"{self.base_url}/api/intercept/{intercept_id}",
                        timeout=self.timeout,
                    )
                    if response.is_error:
                        continue
                    data = response.json()
                    if data.get("decision") in ("approve", "deny"):
                        return data
                except (httpx.HTTPError, ValueError):
                    continue

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
                response = await client.post(
                    f"{self.base_url}/api/session/result",
                    json={
                        "session_id": session_id,
                        "status": status,
                        "intercepts": intercepts,
                    },
                    timeout=self.timeout,
                )
                if response.is_error:
                    return {
                        "error": response.text[:300],
                        "http_status": response.status_code,
                    }
                return response.json()
            except httpx.HTTPError as e:
                return {"error": str(e)}


def create_backend_client() -> BackendClient:
    return BackendClient()
