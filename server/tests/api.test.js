const test = require("node:test");
const assert = require("node:assert/strict");
const http = require("node:http");

process.env.AGENT_SHIELD_DB_PATH = ":memory:";
process.env.TINYFISH_API_KEY = "test-api-key";

const { createApp } = require("../app");
const vulnerabilityIntelService = require("../services/vulnerabilityIntelService");

async function withServer(run) {
  const app = createApp();
  const server = http.createServer(app);

  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const { port } = server.address();
  const baseUrl = `http://127.0.0.1:${port}`;

  try {
    await run(baseUrl);
  } finally {
    await new Promise((resolve, reject) =>
      server.close((error) => (error ? reject(error) : resolve())),
    );
  }
}

test("GET /api/health returns ok", async () => {
  await withServer(async (baseUrl) => {
    const response = await fetch(`${baseUrl}/api/health`);
    assert.equal(response.status, 200);
    assert.deepEqual(await response.json(), { status: "ok" });
  });
});

test("GET /api returns route index", async () => {
  await withServer(async (baseUrl) => {
    const response = await fetch(`${baseUrl}/api`);
    assert.equal(response.status, 200);

    const body = await response.json();
    assert.equal(body.service, "agent-shield-backend");
    assert.ok(body.routes.includes("GET /api/audit"));
    assert.ok(body.routes.includes("POST /api/intercept"));
    assert.ok(body.routes.includes("POST /api/session/result"));
  });
});

test("GET /api/audit returns audit entries", async () => {
  await withServer(async (baseUrl) => {
    const response = await fetch(`${baseUrl}/api/audit?limit=5`);
    assert.equal(response.status, 200);

    const body = await response.json();
    assert.ok(Array.isArray(body));
  });
});

test("requests emit access log lines", async () => {
  const originalLog = console.log;
  const messages = [];
  console.log = (...args) => {
    messages.push(args.join(" "));
  };

  try {
    await withServer(async (baseUrl) => {
      const response = await fetch(`${baseUrl}/api/health`);
      assert.equal(response.status, 200);
    });
  } finally {
    console.log = originalLog;
  }

  assert.ok(messages.some((line) => line.includes("[HTTP] GET /api/health -> 200")));
});

test("intercepts can be created and immediately polled when auto-denied", async () => {
  await withServer(async (baseUrl) => {
    const interceptResponse = await fetch(`${baseUrl}/api/intercept`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: "session-1",
        agent: "codex",
        action_type: "mcp_connection_attempt",
        content: "127.0.0.1:3001",
        risk: {
          risk_level: "high",
          risk_score: 91,
          category: "prompt_injection",
          summary: "Critical outbound MCP target",
          recommended_action: "deny",
          flags: ["mcp", "network"],
        },
      }),
    });

    assert.equal(interceptResponse.status, 200);
    const created = await interceptResponse.json();
    assert.equal(created.status, "decided");
    assert.ok(created.intercept_id);

    const statusResponse = await fetch(
      `${baseUrl}/api/intercept/${created.intercept_id}`,
    );
    assert.equal(statusResponse.status, 200);
    assert.deepEqual(await statusResponse.json(), {
      intercept_id: created.intercept_id,
      status: "decided",
      decision: "deny",
      reason: "Critical outbound MCP target",
    });
  });
});

test("session results are stored with wrapper-compatible response shape", async () => {
  await withServer(async (baseUrl) => {
    const response = await fetch(`${baseUrl}/api/session/result`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: "session-2",
        status: "blocked",
        intercepts: [
          {
            intercept_id: "abc",
            decision: "deny",
            risk_level: "high",
          },
        ],
      }),
    });

    assert.equal(response.status, 200);
    assert.deepEqual(await response.json(), {
      ok: true,
      session_id: "session-2",
    });
  });
});

test("cached vulnerability intel route reads stored findings without invoking Tinyfish", async () => {
  const originalGetStored = vulnerabilityIntelService.getStoredAgentVulnerabilities;

  vulnerabilityIntelService.getStoredAgentVulnerabilities = async () => ({
    table_name: "agent_vulnerability_intel",
    total_findings: 2,
    last_refreshed_at: "2026-03-21T01:00:00.000Z",
    findings: [
      {
        external_id: "prompt-injection-1",
        rank: 1,
        title: "Prompt injection",
        category: "prompt-injection",
        criticity: "critical",
        severity_score: 99,
        summary: "Summary",
        harmful_execution: "Impact",
        exploit_example: "Example",
        potential_fix: "Fix",
        references: [{ title: "OWASP", url: "https://owasp.org/" }],
      },
    ],
  });

  try {
    await withServer(async (baseUrl) => {
      const response = await fetch(`${baseUrl}/api/research/agent-vulnerabilities?limit=5`);
      assert.equal(response.status, 200);

      const body = await response.json();
      assert.equal(body.table_name, "agent_vulnerability_intel");
      assert.equal(body.total_findings, 2);
      assert.equal(body.findings[0].title, "Prompt injection");
    });
  } finally {
    vulnerabilityIntelService.getStoredAgentVulnerabilities = originalGetStored;
  }
});

test("manual vulnerability refresh route can be triggered explicitly", async () => {
  const originalRefresh = vulnerabilityIntelService.refreshStoredAgentVulnerabilities;

  vulnerabilityIntelService.refreshStoredAgentVulnerabilities = async () => ({
    provider: "tinyfish",
    table_name: "agent_vulnerability_intel",
    findings_count: 100,
    last_refreshed_at: "2026-03-21T01:00:00.000Z",
    source_url: "https://www.google.com/",
    goal: "research prompt",
  });

  try {
    await withServer(async (baseUrl) => {
      const response = await fetch(`${baseUrl}/api/research/agent-vulnerabilities/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ limit: 100 }),
      });

      assert.equal(response.status, 200);
      const body = await response.json();
      assert.equal(body.provider, "tinyfish");
      assert.equal(body.findings_count, 100);
      assert.equal(body.table_name, "agent_vulnerability_intel");
    });
  } finally {
    vulnerabilityIntelService.refreshStoredAgentVulnerabilities = originalRefresh;
  }
});
