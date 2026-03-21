const test = require("node:test");
const assert = require("node:assert/strict");
const http = require("node:http");

process.env.AGENT_SHIELD_DB_PATH = ":memory:";
process.env.TINYFISH_API_KEY = "test-api-key";

const { createApp } = require("../app");

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

test("Tinyfish research endpoint returns normalized findings and parameterized postgres SQL", async () => {
  const originalFetch = global.fetch;

  global.fetch = async (url, options) => {
    if (String(url).startsWith("http://127.0.0.1:")) {
      return originalFetch(url, options);
    }

    assert.equal(url, "https://agent.tinyfish.ai/v1/automation/run-sse");
    assert.equal(options.headers["X-API-Key"], "test-api-key");

    return new Response(
      [
        'event: message',
        'data: {"type":"PROGRESS","status":"RUNNING"}',
        "",
        'event: message',
        'data: {"type":"COMPLETE","status":"COMPLETED","result":{"findings":[{"title":"Prompt injection to tool execution","category":"prompt-injection","criticity":"critical","severity_score":98,"summary":"Untrusted content can coerce tool use.","harmful_execution":"Agent follows injected instructions and triggers sensitive tools.","exploit_example":"A web page hides tool-invocation instructions in scraped text.","potential_fix":"Isolate tool plans, require allowlists, and strip untrusted instructions before tool use.","references":[{"title":"OWASP LLM Top 10","url":"https://owasp.org/www-project-top-10-for-large-language-model-applications/"}]},{"title":"Unscoped filesystem MCP access","category":"mcp","criticity":"high","severity_score":88,"summary":"Over-broad filesystem access enables destructive writes.","harmful_execution":"Agent writes or deletes files outside the approved workspace.","exploit_example":"A shell-based MCP wrapper writes startup scripts into user home directories.","potential_fix":"Constrain writable roots and enforce per-tool path policies.","references":[{"title":"Model Context Protocol","url":"https://modelcontextprotocol.io/"}]}]}}',
        "",
      ].join("\n"),
      {
        status: 200,
        headers: { "Content-Type": "text/event-stream" },
      },
    );
  };

  try {
    await withServer(async (baseUrl) => {
      const response = await fetch(`${baseUrl}/api/research/agent-vulnerabilities`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url: "https://www.google.com/",
          limit: 2,
          table_name: "agent_vulnerability_intel",
        }),
      });

      assert.equal(response.status, 200);
      const body = await response.json();

      assert.equal(body.provider, "tinyfish");
      assert.equal(body.findings_count, 2);
      assert.equal(body.findings[0].rank, 1);
      assert.equal(body.findings[0].title, "Prompt injection to tool execution");
      assert.equal(body.postgres.table_name, "agent_vulnerability_intel");
      assert.match(body.postgres.create_table_sql, /CREATE TABLE IF NOT EXISTS agent_vulnerability_intel/);
      assert.match(body.postgres.insert_sql, /INSERT INTO agent_vulnerability_intel/);
      assert.match(body.postgres.insert_sql, /\$1/);
      assert.equal(body.postgres.row_count, 2);
      assert.equal(body.postgres.insert_params.length, 28);
    });
  } finally {
    global.fetch = originalFetch;
  }
});
