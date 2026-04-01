"""Local dashboard for reviewing Agent Shield intercepts.

Serves a single-page HTML dashboard backed by JSON API endpoints.
Designed for `--local-only` mode — no external dependencies beyond the
standard library.

Usage (standalone):
    from local_dashboard import start_dashboard
    server = start_dashboard(interceptor, port=3200)
    # server.shutdown() to stop
"""

import json
import threading
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Any, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from mcp_interceptor import MCPInterceptor


# ---------------------------------------------------------------------------
# Embedded dashboard HTML (single-file, no build step)
# ---------------------------------------------------------------------------

DASHBOARD_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Agent Shield — Local Dashboard</title>
<style>
  :root { --bg:#0d1117; --card:#161b22; --border:#30363d; --text:#c9d1d9;
          --green:#3fb950; --red:#f85149; --yellow:#d29922; --blue:#58a6ff; }
  * { margin:0; padding:0; box-sizing:border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
         background:var(--bg); color:var(--text); padding:24px; }
  h1 { font-size:20px; margin-bottom:4px; }
  .subtitle { color:#8b949e; font-size:13px; margin-bottom:20px; }
  .stats { display:flex; gap:16px; margin-bottom:24px; flex-wrap:wrap; }
  .stat-card { background:var(--card); border:1px solid var(--border); border-radius:8px;
               padding:16px 20px; min-width:140px; }
  .stat-card .label { font-size:12px; color:#8b949e; text-transform:uppercase; letter-spacing:0.5px; }
  .stat-card .value { font-size:28px; font-weight:600; margin-top:4px; }
  .stat-card .value.green { color:var(--green); }
  .stat-card .value.red { color:var(--red); }
  .stat-card .value.yellow { color:var(--yellow); }
  table { width:100%; border-collapse:collapse; background:var(--card);
          border:1px solid var(--border); border-radius:8px; overflow:hidden; }
  th, td { padding:10px 14px; text-align:left; border-bottom:1px solid var(--border); font-size:13px; }
  th { background:#1c2128; color:#8b949e; font-weight:500; text-transform:uppercase; font-size:11px;
       letter-spacing:0.5px; }
  tr:last-child td { border-bottom:none; }
  .badge { display:inline-block; padding:2px 8px; border-radius:12px; font-size:11px; font-weight:600; }
  .badge.approve { background:#238636; color:#fff; }
  .badge.deny { background:#da3633; color:#fff; }
  .badge.low { background:#238636; color:#fff; }
  .badge.medium { background:#9e6a03; color:#fff; }
  .badge.high { background:#da3633; color:#fff; }
  .badge.critical { background:#8b0000; color:#fff; }
  .empty { text-align:center; padding:40px; color:#8b949e; }
  .auto-refresh { font-size:11px; color:#8b949e; margin-top:12px; }
</style>
</head>
<body>
  <h1>Agent Shield</h1>
  <div class="subtitle">Local Dashboard — Session <span id="session">loading…</span></div>

  <div class="stats">
    <div class="stat-card"><div class="label">Agent</div><div class="value" style="font-size:16px" id="agent">—</div></div>
    <div class="stat-card"><div class="label">Status</div><div class="value" id="status">—</div></div>
    <div class="stat-card"><div class="label">Intercepts</div><div class="value" id="total">0</div></div>
    <div class="stat-card"><div class="label">Blocked</div><div class="value red" id="blocked">0</div></div>
    <div class="stat-card"><div class="label">Approved</div><div class="value green" id="approved">0</div></div>
  </div>

  <table>
    <thead><tr>
      <th>Time</th><th>Type</th><th>Role</th><th>Risk</th><th>Decision</th><th>Preview</th>
    </tr></thead>
    <tbody id="intercepts">
      <tr><td colspan="6" class="empty">No intercepts yet — waiting for events…</td></tr>
    </tbody>
  </table>
  <div class="auto-refresh">Auto-refreshes every 2 seconds</div>

<script>
async function poll() {
  try {
    const res = await fetch('/api/state');
    const data = await res.json();
    document.getElementById('session').textContent = data.session_id || '—';
    document.getElementById('agent').textContent = data.agent_name || '—';
    document.getElementById('status').textContent = data.running ? 'running' : 'stopped';
    document.getElementById('total').textContent = data.total_intercepts;
    document.getElementById('blocked').textContent = data.blocked;
    document.getElementById('approved').textContent = data.approved;

    const rows = data.intercepts.map(i => {
      const riskClass = (i.risk_level || '').toLowerCase();
      const decClass = i.decision === 'deny' ? 'deny' : 'approve';
      const time = (i.timestamp || '').slice(11, 19);
      return `<tr>
        <td>${time}</td>
        <td>${i.action_type || ''}</td>
        <td>${i.process_role || ''}</td>
        <td><span class="badge ${riskClass}">${i.risk_level || '?'}</span></td>
        <td><span class="badge ${decClass}">${i.decision || '?'}</span></td>
        <td style="max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(i.content_preview || '')}</td>
      </tr>`;
    }).join('');
    document.getElementById('intercepts').innerHTML = rows || '<tr><td colspan="6" class="empty">No intercepts yet</td></tr>';
  } catch(e) { /* server may not be ready yet */ }
}
function esc(s) { const d=document.createElement('div'); d.textContent=s; return d.innerHTML; }
poll();
setInterval(poll, 2000);
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------

_interceptor_ref: Optional[Any] = None


class _DashboardHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        """Suppress default request logging."""
        pass

    def do_GET(self):
        if self.path == "/":
            self._send_html(DASHBOARD_HTML)
        elif self.path == "/api/state":
            self._send_json(self._build_state())
        elif self.path.startswith("/api/intercepts"):
            state = self._build_state()
            self._send_json(state.get("intercepts", []))
        else:
            self._send_json({"error": "not found"}, status=404)

    def _build_state(self) -> Dict[str, Any]:
        interceptor = _interceptor_ref
        if interceptor is None:
            return {"error": "no interceptor", "intercepts": [], "total_intercepts": 0}

        return {
            "session_id": interceptor.session_id,
            "agent_name": interceptor.agent_name,
            "running": interceptor._running,
            "total_intercepts": len(interceptor.intercepts),
            "blocked": interceptor.blocked_count,
            "approved": interceptor.approved_count,
            "intercepts": list(reversed(interceptor.intercepts)),
        }

    def _send_json(self, data: Any, status: int = 200):
        body = json.dumps(data, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html: str):
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def start_dashboard(
    interceptor: Any,
    port: int = 3200,
    host: str = "127.0.0.1",
) -> HTTPServer:
    """Start the local dashboard in a daemon thread.

    Returns the ``HTTPServer`` instance (call ``.shutdown()`` to stop).
    """
    global _interceptor_ref
    _interceptor_ref = interceptor

    server = HTTPServer((host, port), _DashboardHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server
