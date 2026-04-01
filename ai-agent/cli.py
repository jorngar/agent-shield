#!/usr/bin/env python3
"""
Agent Shield CLI

Wraps an AI coding agent with runtime intercept. Launches the agent as a
subprocess and monitors child processes and network activity, analyzing them
with a local LLM before allowing or blocking.

Usage:
    agent-shield                                  # Run default agent (codex)
    agent-shield --agent kilo
    agent-shield --local-only                     # No backend, local dashboard
    agent-shield --local-only --dashboard         # Local mode with live dashboard
    agent-shield --agent codex -- --help          # Forward args to the agent
    agent-shield --verbose
"""

import argparse
import asyncio
import sys

from config import (
    BACKEND_URL,
    DEFAULT_AGENT,
    INTERCEPT_MODE,
    LOCAL_ONLY,
    VULN_SCAN_ENABLED,
)
from agents import get_adapter, list_adapters
from mcp_interceptor import create_interceptor


def interceptor_mode_display() -> str:
    return INTERCEPT_MODE


async def main():
    available = list_adapters()
    parser = argparse.ArgumentParser(
        description="Agent Shield - AI Agent Runtime Interceptor"
    )
    parser.add_argument("agent_args", nargs="*", help="Arguments to pass to the agent")
    parser.add_argument(
        "--agent",
        default=DEFAULT_AGENT,
        choices=available,
        help="Which AI agent to wrap (default: from AGENT_SHIELD_AGENT env or 'codex')",
    )
    parser.add_argument("--backend", default=BACKEND_URL, help="Backend API URL")
    parser.add_argument(
        "--local-only",
        action="store_true",
        default=LOCAL_ONLY,
        help="Run entirely local — no backend calls, use local risk engine + triage only",
    )
    parser.add_argument(
        "--dashboard",
        action="store_true",
        default=False,
        help="Start local dashboard for reviewing intercepts (implies --local-only unless --backend given)",
    )
    parser.add_argument(
        "--dashboard-port",
        type=int,
        default=None,
        help="Port for local dashboard (default: 3200)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Print interceptor logs to stderr (also always written to log file)",
    )

    args = parser.parse_args()

    # --dashboard without explicit --backend implies --local-only
    if args.dashboard and not args.local_only and args.backend == BACKEND_URL:
        args.local_only = True

    local_only = args.local_only

    adapter_cls = get_adapter(args.agent)
    adapter = adapter_cls()

    print("=" * 50, flush=True)
    print("Agent Shield - AI Agent Runtime Interceptor", flush=True)
    print("=" * 50, flush=True)
    print(f"Agent: {adapter.name}", flush=True)
    if local_only:
        print("Mode: LOCAL ONLY (no backend)", flush=True)
    else:
        print(f"Backend: {args.backend}", flush=True)
    print(f"Intercept Mode: {interceptor_mode_display()}", flush=True)
    print("=" * 50, flush=True)
    print("", flush=True)

    # Vulnerability scan (best-effort, never blocks launch)
    if VULN_SCAN_ENABLED:
        try:
            from vuln_scan import scan_agent_vulnerabilities, format_scan_result

            cmd = adapter.resolve_command(args.agent_args)
            binary = cmd[0] if cmd else args.agent
            scan_result = scan_agent_vulnerabilities(
                agent_name=adapter.name,
                binary=binary,
                logger=lambda msg, **kw: print(msg, flush=True),
            )
            print(format_scan_result(scan_result), flush=True)
            if scan_result.get("vulnerable"):
                print(
                    "[AgentShield] WARNING: vulnerabilities detected. "
                    "Review findings before continuing.",
                    flush=True,
                )
        except Exception as exc:
            print(f"[AgentShield] Vulnerability scan error: {exc}", flush=True)
        print("", flush=True)

    interceptor = create_interceptor(
        adapter=adapter,
        backend_url=args.backend,
        verbose=args.verbose,
        local_only=local_only,
    )

    dashboard_server = None

    if local_only:
        print("[AgentShield] Running in LOCAL-ONLY mode", flush=True)
        if args.dashboard:
            from local_dashboard import start_dashboard

            port = args.dashboard_port or 3200
            dashboard_server = start_dashboard(interceptor, port=port)
            print(
                f"[AgentShield] Dashboard: http://localhost:{port}",
                flush=True,
            )
    else:
        backend_health = await interceptor.backend_client.health_check()
        if backend_health.get("ok"):
            print("[AgentShield] Backend health: ok", flush=True)
        else:
            detail = backend_health.get("http_status") or backend_health.get(
                "error", "unreachable"
            )
            print(f"[AgentShield] Backend health warning: {detail}", flush=True)

    try:
        result = await interceptor.run(agent_args=args.agent_args)

        print("", flush=True)
        print("=" * 50, flush=True)
        print("Session Summary", flush=True)
        print("=" * 50, flush=True)
        print(f"Status: {result['status']}", flush=True)
        print(
            f"Agent Exit: {result.get('codex_exit_display', result.get('codex_exit_code'))}",
            flush=True,
        )
        print(f"Total Intercepts: {result['total_intercepts']}", flush=True)
        print(f"Blocked: {result['blocked']}", flush=True)
        print(f"Approved: {result['approved']}", flush=True)

        if dashboard_server:
            print(
                f"\n[AgentShield] Dashboard still running at http://localhost:{dashboard_server.server_address[1]}",
                flush=True,
            )
            print("[AgentShield] Press Ctrl+C to stop", flush=True)
            try:
                await asyncio.Event().wait()
            except KeyboardInterrupt:
                pass

        sys.exit(0 if result["status"] in ("success", "blocked") else 1)

    except KeyboardInterrupt:
        print("\n[AgentShield] Shutting down...", flush=True)
        interceptor.stop()
        if dashboard_server:
            dashboard_server.shutdown()
        sys.exit(1)
    except Exception as e:
        print(f"[AgentShield] Error: {e}", flush=True)
        if dashboard_server:
            dashboard_server.shutdown()
        sys.exit(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[AgentShield] Interrupted", flush=True)
