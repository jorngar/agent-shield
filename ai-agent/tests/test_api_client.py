import asyncio
import os
import sys
import unittest
from unittest.mock import patch

import httpx

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from api_client import BackendClient


class FakeAsyncClient:
    def __init__(self, response: httpx.Response):
        self.response = response
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, *args, **kwargs):
        self.calls.append(("POST", args, kwargs))
        return self.response

    async def get(self, *args, **kwargs):
        self.calls.append(("GET", args, kwargs))
        return self.response


class BackendClientTests(unittest.TestCase):
    def test_base_url_is_normalized(self):
        client = BackendClient("https://example.execute-api.ap-southeast-1.amazonaws.com/")
        self.assertEqual(
            client.base_url, "https://example.execute-api.ap-southeast-1.amazonaws.com"
        )

    def test_submit_intercept_handles_http_404_without_throwing(self):
        request = httpx.Request("POST", "http://localhost:3000/api/intercept")
        response = httpx.Response(404, request=request, text="not found")
        fake_client = FakeAsyncClient(response)

        with patch(
            "api_client.httpx.AsyncClient", return_value=fake_client
        ):
            client = BackendClient("http://localhost:3000")
            result = asyncio.run(
                client.submit_intercept(
                    session_id="s1",
                    agent="codex",
                    action_type="mcp_connection_attempt",
                    content="127.0.0.1:3001",
                    risk={"risk_level": "high"},
                )
            )

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["http_status"], 404)
        self.assertEqual(fake_client.calls[0][1][0], "http://localhost:3000/api/intercept")

    def test_report_session_result_handles_http_404_without_throwing(self):
        request = httpx.Request("POST", "http://localhost:3000/api/session/result")
        response = httpx.Response(404, request=request, text="not found")
        fake_client = FakeAsyncClient(response)

        with patch(
            "api_client.httpx.AsyncClient", return_value=fake_client
        ):
            client = BackendClient("http://localhost:3000")
            result = asyncio.run(
                client.report_session_result(
                    session_id="s1", status="failed", intercepts=[]
                )
            )

        self.assertEqual(result["http_status"], 404)
        self.assertIn("error", result)
        self.assertEqual(
            fake_client.calls[0][1][0],
            "http://localhost:3000/api/session/result",
        )

    def test_health_check_returns_ok_for_success_response(self):
        request = httpx.Request("GET", "http://localhost:3000/api/health")
        response = httpx.Response(200, request=request, json={"status": "ok"})
        fake_client = FakeAsyncClient(response)

        with patch(
            "api_client.httpx.AsyncClient", return_value=fake_client
        ):
            client = BackendClient("http://localhost:3000")
            result = asyncio.run(client.health_check())

        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "ok")
        self.assertEqual(fake_client.calls[0][1][0], "http://localhost:3000/api/health")

    def test_base_url_with_api_suffix_does_not_double_prefix_routes(self):
        request = httpx.Request(
            "POST", "https://example.execute-api.ap-southeast-1.amazonaws.com/api/intercept"
        )
        response = httpx.Response(200, request=request, json={"intercept_id": "x", "status": "pending"})
        fake_client = FakeAsyncClient(response)

        with patch(
            "api_client.httpx.AsyncClient", return_value=fake_client
        ):
            client = BackendClient("https://example.execute-api.ap-southeast-1.amazonaws.com/api")
            result = asyncio.run(
                client.submit_intercept(
                    session_id="s1",
                    agent="codex",
                    action_type="agent_connection_attempt",
                    content="test",
                    risk={"risk_level": "medium"},
                )
            )

        self.assertEqual(result["status"], "pending")
        self.assertEqual(
            fake_client.calls[0][1][0],
            "https://example.execute-api.ap-southeast-1.amazonaws.com/api/intercept",
        )


if __name__ == "__main__":
    unittest.main()
