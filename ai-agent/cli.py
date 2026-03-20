#!/usr/bin/env python3
"""
Agent Shield CLI

Wraps Codex with MCP interception. Runs Codex as a subprocess and
monitors for MCP server connections, analyzing them with Qwen before
allowing or blocking.

Usage:
    python cli.py                      # Run Codex normally
    python cli.py --allow-fs           # Allow filesystem MCP
    python cli.py -- verbose           # Verbose output
"""

import argparse
import asyncio
import sys
from mcp_interceptor import create_interceptor


async def main():
    parser = argparse.ArgumentParser(description="Agent Shield - Codex MCP Interceptor")
    parser.add_argument("codex_args", nargs="*", help="Arguments to pass to Codex")
    parser.add_argument(
        "--backend", default="http://localhost:3000", help="Backend API URL"
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    args = parser.parse_args()

    print("=" * 50)
    print("Agent Shield - Codex MCP Interceptor")
    print("=" * 50)
    print(f"Backend: {args.backend}")
    print("=" * 50)
    print()

    interceptor = create_interceptor(backend_url=args.backend, agent_name="codex")

    try:
        result = await interceptor.run(codex_args=args.codex_args)

        print()
        print("=" * 50)
        print("Session Summary")
        print("=" * 50)
        print(f"Status: {result['status']}")
        print(f"Codex Exit: {result.get('codex_exit_code')}")
        print(f"Total Intercepts: {result['total_intercepts']}")
        print(f"Blocked: {result['blocked']}")
        print(f"Approved: {result['approved']}")

        sys.exit(0 if result["status"] in ("success", "blocked") else 1)

    except KeyboardInterrupt:
        print("\n[AgentShield] Shutting down...")
        interceptor.stop()
        sys.exit(1)
    except Exception as e:
        print(f"[AgentShield] Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
