const DEFAULT_FINDINGS_LIMIT = 100;
const DEFAULT_TABLE_NAME = "agent_vulnerability_intel";
const TINYFISH_SSE_URL = "https://agent.tinyfish.ai/v1/automation/run-sse";

const DEFAULT_RESEARCH_GOAL =
  "search for the up to date top 100 ai agent vulnerabilities, exploits and possible harmful executions across the web for me, rank them with criticity and show me potential fixes for them and examples of how can they look";

function buildTinyfishGoal(baseGoal, limit) {
  return [
    baseGoal || DEFAULT_RESEARCH_GOAL,
    `Return JSON only with a top-level "findings" array containing up to ${limit} items.`,
    'Each item must include: "title", "category", "criticity", "severity_score", "summary", "harmful_execution", "exploit_example", "potential_fix", and "references".',
    'Use "references" as an array of objects with "title" and "url".',
    'Rank the findings from most critical to least critical.',
    "Only include vulnerabilities relevant to AI agents, MCP/tool use, browser automation, prompt injection, shell execution, file writes, data exfiltration, code execution, supply chain compromise, model/tool hijacking, authentication bypass, or memory poisoning.",
    "Examples must stay high level and defensive. Do not provide step-by-step exploit instructions.",
    "If the web does not support exactly 100 credible items, return the most credible current set up to the requested limit.",
  ].join(" ");
}

function parseInteger(value, fallback) {
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function clampLimit(value) {
  return Math.max(1, Math.min(DEFAULT_FINDINGS_LIMIT, parseInteger(value, DEFAULT_FINDINGS_LIMIT)));
}

function slugify(value) {
  return String(value || "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 80);
}

function normalizeCriticity(value) {
  const normalized = String(value || "")
    .trim()
    .toLowerCase();

  if (["critical", "crit", "severe"].includes(normalized)) {
    return "critical";
  }
  if (["high", "elevated"].includes(normalized)) {
    return "high";
  }
  if (["low", "minor"].includes(normalized)) {
    return "low";
  }

  return "medium";
}

function defaultSeverityForCriticity(criticity) {
  switch (criticity) {
    case "critical":
      return 95;
    case "high":
      return 80;
    case "medium":
      return 55;
    case "low":
      return 25;
    default:
      return 50;
  }
}

function normalizeSeverityScore(value, criticity) {
  const parsed = Number.parseInt(value, 10);
  if (Number.isFinite(parsed)) {
    return Math.max(0, Math.min(100, parsed));
  }
  return defaultSeverityForCriticity(criticity);
}

function cleanText(value) {
  return String(value || "")
    .replace(/\s+/g, " ")
    .trim();
}

function normalizeReferences(value) {
  if (!Array.isArray(value)) {
    return [];
  }

  return value
    .map((entry) => {
      if (!entry) {
        return null;
      }

      if (typeof entry === "string") {
        try {
          const url = new URL(entry);
          return { title: url.hostname, url: url.toString() };
        } catch {
          return null;
        }
      }

      const rawUrl = cleanText(entry.url || entry.href || entry.link);
      if (!rawUrl) {
        return null;
      }

      try {
        const url = new URL(rawUrl);
        return {
          title: cleanText(entry.title || entry.name || url.hostname) || url.hostname,
          url: url.toString(),
        };
      } catch {
        return null;
      }
    })
    .filter(Boolean);
}

function extractStructuredResult(value) {
  if (!value) {
    return null;
  }

  if (typeof value === "string") {
    const trimmed = value.trim();
    if (!trimmed) {
      return null;
    }

    try {
      return JSON.parse(trimmed);
    } catch {
      const match = trimmed.match(/\{[\s\S]*\}|\[[\s\S]*\]/);
      if (!match) {
        return null;
      }

      try {
        return JSON.parse(match[0]);
      } catch {
        return null;
      }
    }
  }

  if (typeof value === "object") {
    return value;
  }

  return null;
}

function extractFindingsCandidate(payload) {
  if (Array.isArray(payload)) {
    return payload;
  }

  if (!payload || typeof payload !== "object") {
    return [];
  }

  return (
    payload.findings ||
    payload.vulnerabilities ||
    payload.results ||
    payload.items ||
    payload.entries ||
    []
  );
}

function normalizeFinding(entry, index) {
  if (!entry || typeof entry !== "object") {
    return null;
  }

  const title = cleanText(entry.title || entry.name || entry.vulnerability);
  if (!title) {
    return null;
  }

  const criticity = normalizeCriticity(
    entry.criticity || entry.criticality || entry.severity || entry.risk_level,
  );
  const severityScore = normalizeSeverityScore(
    entry.severity_score || entry.risk_score || entry.score,
    criticity,
  );
  const summary = cleanText(entry.summary || entry.description || entry.overview || title);
  const harmfulExecution = cleanText(
    entry.harmful_execution || entry.attack_chain || entry.impact || entry.exploit || summary,
  );
  const exploitExample = cleanText(
    entry.exploit_example || entry.example || entry.example_execution || harmfulExecution,
  );
  const potentialFix = cleanText(
    entry.potential_fix || entry.fix || entry.remediation || entry.mitigation,
  );
  const category = cleanText(entry.category || entry.type || "agent-security");

  if (!potentialFix) {
    return null;
  }

  return {
    external_id:
      cleanText(entry.external_id || entry.id || entry.slug) ||
      `${slugify(title)}-${index + 1}`,
    title,
    category,
    criticity,
    severity_score: severityScore,
    summary,
    harmful_execution: harmfulExecution,
    exploit_example: exploitExample,
    potential_fix: potentialFix,
    references: normalizeReferences(entry.references || entry.sources || entry.links),
  };
}

function normalizeFindings(payload, limit) {
  const findings = extractFindingsCandidate(payload);
  if (!Array.isArray(findings)) {
    throw new Error("Tinyfish result did not include a findings array");
  }

  const normalized = findings
    .map(normalizeFinding)
    .filter(Boolean)
    .sort((left, right) => right.severity_score - left.severity_score)
    .slice(0, limit)
    .map((finding, index) => ({ ...finding, rank: index + 1 }));

  if (!normalized.length) {
    throw new Error("Tinyfish returned no valid vulnerability findings");
  }

  return normalized;
}

function assertTableName(tableName) {
  if (!/^[a-z_][a-z0-9_]*$/i.test(tableName)) {
    throw new Error("table_name must contain only letters, numbers, and underscores");
  }
}

function buildPostgresInsert(findings, options = {}) {
  const tableName = options.tableName || DEFAULT_TABLE_NAME;
  const sourceProvider = options.sourceProvider || "tinyfish";
  const researchGoal = cleanText(options.researchGoal || DEFAULT_RESEARCH_GOAL);
  const collectedAt = options.collectedAt || new Date().toISOString();

  assertTableName(tableName);

  const columns = [
    "external_id",
    "rank",
    "title",
    "category",
    "criticity",
    "severity_score",
    "summary",
    "harmful_execution",
    "exploit_example",
    "potential_fix",
    "references_json",
    "source_provider",
    "research_goal",
    "collected_at",
  ];

  const params = [];
  const values = findings.map((finding) => {
    params.push(
      finding.external_id,
      finding.rank,
      finding.title,
      finding.category,
      finding.criticity,
      finding.severity_score,
      finding.summary,
      finding.harmful_execution,
      finding.exploit_example,
      finding.potential_fix,
      JSON.stringify(finding.references),
      sourceProvider,
      researchGoal,
      collectedAt,
    );

    const startIndex = params.length - columns.length + 1;
    const placeholders = columns.map((_, index) => `$${startIndex + index}`);
    return `(${placeholders.join(", ")})`;
  });

  const createTableSql = `
CREATE TABLE IF NOT EXISTS ${tableName} (
  external_id TEXT PRIMARY KEY,
  rank INTEGER NOT NULL,
  title TEXT NOT NULL,
  category TEXT NOT NULL,
  criticity TEXT NOT NULL,
  severity_score INTEGER NOT NULL CHECK (severity_score >= 0 AND severity_score <= 100),
  summary TEXT NOT NULL,
  harmful_execution TEXT NOT NULL,
  exploit_example TEXT NOT NULL,
  potential_fix TEXT NOT NULL,
  references_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  source_provider TEXT NOT NULL,
  research_goal TEXT NOT NULL,
  collected_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);`.trim();

  const insertSql = `
INSERT INTO ${tableName} (${columns.join(", ")})
VALUES
  ${values.join(",\n  ")}
ON CONFLICT (external_id) DO UPDATE SET
  rank = EXCLUDED.rank,
  title = EXCLUDED.title,
  category = EXCLUDED.category,
  criticity = EXCLUDED.criticity,
  severity_score = EXCLUDED.severity_score,
  summary = EXCLUDED.summary,
  harmful_execution = EXCLUDED.harmful_execution,
  exploit_example = EXCLUDED.exploit_example,
  potential_fix = EXCLUDED.potential_fix,
  references_json = EXCLUDED.references_json,
  source_provider = EXCLUDED.source_provider,
  research_goal = EXCLUDED.research_goal,
  collected_at = EXCLUDED.collected_at;`.trim();

  return {
    table_name: tableName,
    create_table_sql: createTableSql,
    insert_sql: insertSql,
    insert_params: params,
    row_count: findings.length,
  };
}

function parseSseEvent(rawEvent) {
  const lines = rawEvent
    .split(/\r?\n/)
    .map((line) => line.trimEnd())
    .filter(Boolean);

  if (!lines.length) {
    return null;
  }

  const dataLines = [];
  let eventName = "message";

  for (const line of lines) {
    if (line.startsWith("event:")) {
      eventName = line.slice(6).trim() || eventName;
      continue;
    }

    if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trim());
    }
  }

  if (!dataLines.length) {
    return null;
  }

  const data = dataLines.join("\n");
  const payload = extractStructuredResult(data) ?? data;

  return { event: eventName, data, payload };
}

async function collectTinyfishResult(response) {
  const reader = response.body?.getReader();
  if (!reader) {
    throw new Error("Tinyfish response is missing a body");
  }

  const decoder = new TextDecoder();
  let buffer = "";
  const events = [];
  let lastPayload = null;

  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });

    let separatorIndex = buffer.indexOf("\n\n");
    while (separatorIndex !== -1) {
      const rawEvent = buffer.slice(0, separatorIndex);
      buffer = buffer.slice(separatorIndex + 2);
      const event = parseSseEvent(rawEvent);
      if (event) {
        events.push(event);
        lastPayload = event.payload;

        const payload = event.payload;
        if (payload && typeof payload === "object") {
          const status = String(payload.status || "").toUpperCase();
          const type = String(payload.type || "").toUpperCase();
          if (status === "FAILED" || type === "ERROR") {
            throw new Error(payload.error?.message || payload.message || "Tinyfish automation failed");
          }
          if (status === "COMPLETED" || type === "COMPLETE") {
            return { events, result: payload.result ?? payload };
          }
        }
      }

      separatorIndex = buffer.indexOf("\n\n");
    }

    if (done) {
      break;
    }
  }

  if (buffer.trim()) {
    const event = parseSseEvent(buffer);
    if (event) {
      events.push(event);
      lastPayload = event.payload;

      const payload = event.payload;
      if (payload && typeof payload === "object") {
        const status = String(payload.status || "").toUpperCase();
        const type = String(payload.type || "").toUpperCase();
        if (status === "FAILED" || type === "ERROR") {
          throw new Error(payload.error?.message || payload.message || "Tinyfish automation failed");
        }
        if (status === "COMPLETED" || type === "COMPLETE") {
          return { events, result: payload.result ?? payload };
        }
      }
    }
  }

  return { events, result: lastPayload?.result ?? lastPayload };
}

async function runTinyfishAutomation(options = {}) {
  const apiKey = process.env.TINYFISH_API_KEY;
  if (!apiKey) {
    throw new Error("Missing TINYFISH_API_KEY");
  }

  const fetchImpl = options.fetchImpl || global.fetch;
  if (typeof fetchImpl !== "function") {
    throw new Error("Fetch is unavailable in the current Node runtime");
  }

  const payload = {
    url: options.url || process.env.TINYFISH_RESEARCH_URL || "https://www.google.com/",
    goal: buildTinyfishGoal(options.goal, options.limit || DEFAULT_FINDINGS_LIMIT),
    browser_profile: options.browserProfile || process.env.TINYFISH_BROWSER_PROFILE || "lite",
    api_integration: "agent-shield",
  };

  const response = await fetchImpl(TINYFISH_SSE_URL, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-API-Key": apiKey,
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const errorBody = await response.text();
    throw new Error(`Tinyfish request failed with ${response.status}: ${errorBody.slice(0, 400)}`);
  }

  return collectTinyfishResult(response);
}

async function researchAgentVulnerabilities(options = {}) {
  const limit = clampLimit(options.limit);
  const goal = options.goal || DEFAULT_RESEARCH_GOAL;
  const tableName = options.tableName || DEFAULT_TABLE_NAME;
  const collectedAt = new Date().toISOString();

  const tinyfish = await runTinyfishAutomation({
    url: options.url,
    goal,
    limit,
    browserProfile: options.browserProfile,
    fetchImpl: options.fetchImpl,
  });

  const structuredResult = extractStructuredResult(tinyfish.result);
  if (!structuredResult) {
    throw new Error("Tinyfish returned an unstructured result payload");
  }

  const findings = normalizeFindings(structuredResult, limit);
  const postgres = buildPostgresInsert(findings, {
    tableName,
    sourceProvider: "tinyfish",
    researchGoal: goal,
    collectedAt,
  });

  return {
    provider: "tinyfish",
    source_url: options.url || process.env.TINYFISH_RESEARCH_URL || "https://www.google.com/",
    browser_profile:
      options.browserProfile || process.env.TINYFISH_BROWSER_PROFILE || "lite",
    goal,
    findings_count: findings.length,
    findings,
    postgres,
    collected_at: collectedAt,
  };
}

module.exports = {
  DEFAULT_FINDINGS_LIMIT,
  DEFAULT_RESEARCH_GOAL,
  buildPostgresInsert,
  buildTinyfishGoal,
  normalizeFindings,
  parseSseEvent,
  researchAgentVulnerabilities,
};
