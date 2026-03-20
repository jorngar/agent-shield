import type { Intercept, RiskLevel } from "@/lib/types";

const BASE_URL = (import.meta.env.VITE_API_URL as string | undefined) ?? "http://localhost:3001";

// ── Raw API shapes ──────────────────────────────────────────────────────────

export interface ApiIntercept {
  id: number;
  timestamp: string;
  tool_name: string;
  tool_args: string;        // JSON-stringified object
  summary: string;
  verdict: "approve" | "deny" | "pending";
  reason: string;
}

// ── HTTP helpers ────────────────────────────────────────────────────────────

export async function fetchAuditLog(limit = 100): Promise<ApiIntercept[]> {
  const res = await fetch(`${BASE_URL}/audit?limit=${limit}`, { signal: AbortSignal.timeout(8000) });
  if (!res.ok) throw new Error(`GET /audit → ${res.status}`);
  return res.json() as Promise<ApiIntercept[]>;
}

export async function patchDecision(
  id: number,
  verdict: "approve" | "deny",
): Promise<void> {
  const res = await fetch(`${BASE_URL}/audit/${id}/decision`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ verdict }),
    signal: AbortSignal.timeout(8000),
  });
  if (!res.ok && res.status !== 501) {
    throw new Error(`PATCH /audit/${id}/decision → ${res.status}`);
  }
}

// ── Field derivation ────────────────────────────────────────────────────────

const VERDICT_TO_STATUS = {
  approve: "approved",
  deny:    "denied",
  pending: "pending",
} as const;

function deriveRiskLevel(reason: string, verdict: ApiIntercept["verdict"]): RiskLevel {
  if (
    verdict === "deny" ||
    /blocked|danger|critical|delete|drop|rm\s+-rf|secret|password|credential|token/i.test(reason)
  ) return "high";

  if (
    verdict === "pending" ||
    /review|write|modify|update|send|post|patch/i.test(reason)
  ) return "medium";

  return "low";
}

function deriveCategory(toolName: string): string {
  if (/file|write|read|mkdir|path|dir/i.test(toolName))         return "File System";
  if (/database|db|sql|query|table|mongo/i.test(toolName))      return "Database";
  if (/email|smtp|http|request|fetch|api|webhook/i.test(toolName)) return "Network";
  if (/python|bash|exec|run|shell|script|eval/i.test(toolName)) return "Code Execution";
  if (/secret|key|token|cred|env|vault/i.test(toolName))        return "Secrets";
  return "System";
}

function extractMatchedRules(reason: string): string[] {
  // "Contains review keyword: write" → ["keyword:write"]
  // "Contains blocked keyword: delete" → ["blocked:delete"]
  const results: string[] = [];

  const kwMatch = reason.match(/(?:blocked\s+)?keyword[s]?:\s*(\w+)/gi);
  if (kwMatch) {
    kwMatch.forEach((m) => {
      const isBlocked = /blocked/i.test(m);
      const word = m.replace(/.*keyword[s]?:\s*/i, "").trim();
      results.push(isBlocked ? `blocked:${word}` : `keyword:${word}`);
    });
    return results;
  }

  // Fallback: first ~40 chars of reason as a rule tag
  return [reason.length > 40 ? reason.slice(0, 40) + "…" : reason];
}

// ── Map API → Intercept ─────────────────────────────────────────────────────

export function mapApiIntercept(api: ApiIntercept): Intercept {
  const riskLevel = deriveRiskLevel(api.reason, api.verdict);
  const status    = VERDICT_TO_STATUS[api.verdict];

  let parsedArgs: Record<string, unknown> = {};
  if (api.tool_args) {
    try {
      parsedArgs = typeof api.tool_args === "string"
        ? JSON.parse(api.tool_args)
        : (api.tool_args as Record<string, unknown>);
    } catch {
      parsedArgs = { raw: api.tool_args };
    }
  }

  const confidenceByRisk: Record<RiskLevel, number> = {
    high:   0.91,
    medium: 0.76,
    low:    0.60,
  };

  return {
    id:           String(api.id),
    toolName:     api.tool_name,
    status,
    riskLevel,
    category:     deriveCategory(api.tool_name),
    confidence:   confidenceByRisk[riskLevel],
    reason:       api.summary ?? api.reason,
    timestamp:    api.timestamp,
    decidedAt:    status !== "pending" ? api.timestamp : undefined,
    arguments:    parsedArgs,
    matchedRules: extractMatchedRules(api.reason),
  };
}
