#!/usr/bin/env python3
"""
Agent Shield CLI

Wraps Codex with runtime intercept. Runs Codex as a subprocess and
monitors child processes and network activity, analyzing them with Qwen before
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
from config import BACKEND_URL, INTERCEPT_MODE
from mcp_interceptor import create_interceptor


def interceptor_mode_display() -> str:
    return INTERCEPT_MODE


async def main():
    parser = argparse.ArgumentParser(description="Agent Shield - Codex Runtime Interceptor")
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
    print("Agent Shield - Codex Runtime Interceptor", flush=True)
    print("=" * 50, flush=True)
    print(f"Backend: {args.backend}", flush=True)
    print(f"Intercept Mode: {interceptor_mode_display()}", flush=True)
    print("=" * 50, flush=True)
    print("", flush=True)

    interceptor = create_interceptor(
        backend_url=args.backend,
        agent_name="codex",
        verbose=args.verbose,
    )

    backend_health = await interceptor.backend_client.health_check()
    if backend_health.get("ok"):
        print("[AgentShield] Backend health: ok", flush=True)
    else:
        detail = backend_health.get("http_status") or backend_health.get("error", "unreachable")
        print(f"[AgentShield] Backend health warning: {detail}", flush=True)

    try:
        result = await interceptor.run(codex_args=args.codex_args)

        print("", flush=True)
        print("=" * 50, flush=True)
        print("Session Summary", flush=True)
        print("=" * 50, flush=True)
        print(f"Status: {result['status']}", flush=True)
        print(
            f"Codex Exit: {result.get('codex_exit_display', result.get('codex_exit_code'))}",
            flush=True,
        )
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
