import type { Intercept, RiskLevel } from "@/lib/types";

const BASE_URL = `${(import.meta.env.VITE_API_URL as string | undefined) ?? "http://localhost:3001"}`;

// ── Raw API shapes ──────────────────────────────────────────────────────────

export interface ApiIntercept {
  id: number;
  created_at: string;
  action_type: string;
  content: string;          // JSON-stringified object
  risk_summary: string;
  risk_level: string;
  risk_category: string;
  verdict: "approve" | "deny" | "pending";
  reason: string;
}

// ── HTTP helpers ────────────────────────────────────────────────────────────

export async function fetchAuditLog(limit = 100): Promise<ApiIntercept[]> {
  const res = await fetch(`${BASE_URL}/api/audit/all?limit=${limit}`, { signal: AbortSignal.timeout(8000) });
  if (!res.ok) throw new Error(`GET /api/audit/all → ${res.status}`);
  return res.json() as Promise<ApiIntercept[]>;
}

export async function patchDecision(
  id: number,
  verdict: "approve" | "deny",
): Promise<void> {
  const res = await fetch(`${BASE_URL}/intercept/${id}/decision`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ decision: verdict }),
    signal: AbortSignal.timeout(8000),
  });
  if (!res.ok && res.status !== 501) {
    throw new Error(`PUT /api/intercept/${id}/decision → ${res.status}`);
  }
}

// ── Field derivation ────────────────────────────────────────────────────────

const VERDICT_TO_STATUS = {
  approve: "approved",
  deny:    "denied",
  pending: "pending",
} as const;

function deriveRiskLevel(api: ApiIntercept): RiskLevel {
  if (api.risk_level) {
    const lvl = api.risk_level.toLowerCase();
    if (lvl === "high" || lvl === "critical") return "high";
    if (lvl === "medium")                      return "medium";
    if (lvl === "low")                         return "low";
  }
  if (
    api.verdict === "deny" ||
    /blocked|danger|critical|delete|drop|rm\s+-rf|secret|password|credential|token/i.test(api.reason)
  ) return "high";
  if (
    api.verdict === "pending" ||
    /review|write|modify|update|send|post|patch/i.test(api.reason)
  ) return "medium";
  return "low";
}

function deriveCategory(api: ApiIntercept): string {
  if (api.risk_category) return api.risk_category;
  const t = api.action_type ?? "";
  if (/file|write|read|mkdir|path|dir/i.test(t))            return "File System";
  if (/database|db|sql|query|table|mongo/i.test(t))         return "Database";
  if (/email|smtp|http|request|fetch|api|webhook/i.test(t)) return "Network";
  if (/python|bash|exec|run|shell|script|eval/i.test(t))    return "Code Execution";
  if (/secret|key|token|cred|env|vault/i.test(t))           return "Secrets";
  return "System";
}

function extractMatchedRules(reason: string): string[] {
  const kwMatch = reason.match(/(?:blocked\s+)?keyword[s]?:\s*(\w+)/gi);
  if (kwMatch) {
    return kwMatch.map((m) => {
      const isBlocked = /blocked/i.test(m);
      const word = m.replace(/.*keyword[s]?:\s*/i, "").trim();
      return isBlocked ? `blocked:${word}` : `keyword:${word}`;
    });
  }
  return [reason.length > 40 ? reason.slice(0, 40) + "…" : reason];
}

// ── Map API → Intercept ─────────────────────────────────────────────────────

export function mapApiIntercept(api: ApiIntercept): Intercept {
  const riskLevel = deriveRiskLevel(api);
  const status    = VERDICT_TO_STATUS[api.verdict];

  let parsedArgs: Record<string, unknown> = {};
  if (api.content) {
    try {
      parsedArgs = typeof api.content === "string"
        ? JSON.parse(api.content)
        : (api.content as Record<string, unknown>);
    } catch {
      parsedArgs = { raw: api.content };
    }
  }

  const confidenceByRisk: Record<RiskLevel, number> = {
    high:   0.91,
    medium: 0.76,
    low:    0.60,
  };

  return {
    id:           String(api.id),
    toolName:     api.action_type,
    status,
    riskLevel,
    category:     deriveCategory(api),
    confidence:   confidenceByRisk[riskLevel],
    reason:       api.risk_summary ?? api.reason,
    timestamp:    api.created_at,
    decidedAt:    status !== "pending" ? api.created_at : undefined,
    arguments:    parsedArgs,
    matchedRules: extractMatchedRules(api.reason),
  };
}
