const test = require("node:test");
const assert = require("node:assert/strict");

process.env.TINYFISH_API_KEY = "test-api-key";

const {
  researchAgentVulnerabilities,
} = require("../services/tinyfishResearchService");

test("researchAgentVulnerabilities parses SSE and builds parameterized postgres SQL", async () => {
  const fetchImpl = async (url, options) => {
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

  const result = await researchAgentVulnerabilities({
    url: "https://www.google.com/",
    limit: 2,
    tableName: "agent_vulnerability_intel",
    fetchImpl,
  });

  assert.equal(result.provider, "tinyfish");
  assert.equal(result.findings_count, 2);
  assert.equal(result.findings[0].rank, 1);
  assert.equal(result.findings[0].title, "Prompt injection to tool execution");
  assert.equal(result.postgres.table_name, "agent_vulnerability_intel");
  assert.match(result.postgres.create_table_sql, /CREATE TABLE IF NOT EXISTS agent_vulnerability_intel/);
  assert.match(result.postgres.insert_sql, /INSERT INTO agent_vulnerability_intel/);
  assert.match(result.postgres.insert_sql, /\$1/);
  assert.equal(result.postgres.row_count, 2);
  assert.equal(result.postgres.insert_params.length, 28);
});
