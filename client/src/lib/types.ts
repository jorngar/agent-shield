export type RiskLevel = "low" | "medium" | "high";
export type DecisionStatus = "pending" | "approved" | "denied";

export interface Intercept {
  id: string;
  toolName: string;
  status: DecisionStatus;
  riskLevel: RiskLevel;
  category: string;
  confidence: number;
  reason: string;
  timestamp: string;
  decidedAt?: string;
  arguments: Record<string, unknown>;
  matchedRules: string[];
}
