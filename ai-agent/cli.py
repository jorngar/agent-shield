#!/usr/bin/env python3
"""
Agent Shield CLI

Wraps Codex with MCP interception. Runs Codex as a subprocess and
monitors for MCP server connections, analyzing them with Qwen before
allowing or blocking.

Usage:
    python cli.py                                  # Run Codex normally
    python cli.py --backend http://localhost:3000
    python cli.py -- --help                        # Forward args to Codex
    python cli.py --verbose
"""

import argparse
import asyncio
import sys
from config import BACKEND_URL
from mcp_interceptor import create_interceptor


async def main():
    parser = argparse.ArgumentParser(description="Agent Shield - Codex MCP Interceptor")
    parser.add_argument("codex_args", nargs="*", help="Arguments to pass to Codex")
    parser.add_argument(
        "--backend", default=BACKEND_URL, help="Backend API URL"
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Print interceptor logs to stderr (also always written to log file)",
    )

    args = parser.parse_args()

    print("=" * 50, flush=True)
    print("Agent Shield - Codex MCP Interceptor", flush=True)
    print("=" * 50, flush=True)
    print(f"Backend: {args.backend}", flush=True)
    print("=" * 50, flush=True)
    print("", flush=True)

    interceptor = create_interceptor(
        backend_url=args.backend,
        agent_name="codex",
        verbose=args.verbose,
    )

    try:
        result = await interceptor.run(codex_args=args.codex_args)

        print("", flush=True)
        print("=" * 50, flush=True)
        print("Session Summary", flush=True)
        print("=" * 50, flush=True)
        print(f"Status: {result['status']}", flush=True)
        print(f"Codex Exit: {result.get('codex_exit_code')}", flush=True)
        print(f"Total Intercepts: {result['total_intercepts']}", flush=True)
        print(f"Blocked: {result['blocked']}", flush=True)
        print(f"Approved: {result['approved']}", flush=True)

        sys.exit(0 if result["status"] in ("success", "blocked") else 1)

    except KeyboardInterrupt:
        print("\n[AgentShield] Shutting down...", flush=True)
        interceptor.stop()
        sys.exit(1)
    except Exception as e:
        print(f"[AgentShield] Error: {e}", flush=True)
        sys.exit(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[AgentShield] Interrupted", flush=True)
