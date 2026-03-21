import { useState, useEffect, useCallback } from "react";
import { ref, onValue, off, update } from "firebase/database";
import { rtdb } from "@/lib/firebase";
import type { Intercept, DecisionStatus } from "@/lib/types";
import { mockIntercepts } from "@/lib/mock-data";
import { useApiIntercepts } from "./useApiIntercepts";
import { patchDecision } from "@/lib/api";

export interface UseInterceptsReturn {
  intercepts: Intercept[];
  isLoading: boolean;
  error: string | null;
  lastUpdated: Date | null;
  decide: (id: string, decision: Exclude<DecisionStatus, "pending">, reason?: string) => Promise<void>;
  retry: () => void;
}

// Priority: Firebase RTDB > REST API > Mock
const API_CONFIGURED      = Boolean(import.meta.env.VITE_API_URL);
const FIREBASE_CONFIGURED = Boolean(import.meta.env.VITE_FIREBASE_DATABASE_URL);

// ── Map RTDB doc → Intercept ─────────────────────────────────────────────────
function rtdbDocToIntercept(interceptId: string, data: Record<string, unknown>): Intercept {
  const risk = (data.risk ?? {}) as Record<string, unknown>;

  const userSelected = data.user_selected as string | null;
  let status: Intercept["status"] = "pending";
  if (userSelected === "approve") status = "approved";
  else if (userSelected === "deny") status = "denied";

  const riskLevel = (() => {
    const lvl = String(risk.risk_level ?? "").toLowerCase();
    if (lvl === "high" || lvl === "critical") return "high" as const;
    if (lvl === "medium")                      return "medium" as const;
    return "low" as const;
  })();

  let parsedArgs: Record<string, unknown> = {};
  if (data.content) {
    try {
      parsedArgs = typeof data.content === "string"
        ? JSON.parse(data.content as string)
        : (data.content as Record<string, unknown>);
    } catch {
      parsedArgs = { raw: data.content };
    }
  }

  const confidenceByRisk = { high: 0.91, medium: 0.76, low: 0.60 };

  return {
    id:           interceptId,
    toolName:     String(data.action_type ?? ""),
    status,
    riskLevel,
    category:     String(risk.category ?? "System"),
    confidence:   Number(risk.risk_score ?? confidenceByRisk[riskLevel]),
    reason:       String(risk.summary ?? data.reason ?? ""),
    timestamp:    typeof data.timestamp === "number"
                    ? new Date(data.timestamp).toISOString()
                    : new Date().toISOString(),
    decidedAt:      data.decided_at
                      ? new Date(data.decided_at as number).toISOString()
                      : undefined,
    decisionReason: data.decision_reason ? String(data.decision_reason) : undefined,
    arguments:      parsedArgs,
    matchedRules: Array.isArray(risk.flags)
                    ? (risk.flags as string[])
                    : [String(data.reason ?? "").slice(0, 40)],
  };
}

// ── Mock fallback ────────────────────────────────────────────────────────────
function useMockIntercepts(): UseInterceptsReturn {
  const [intercepts, setIntercepts]   = useState<Intercept[]>([]);
  const [isLoading, setIsLoading]     = useState(true);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  useEffect(() => {
    const t = setTimeout(() => {
      setIntercepts(mockIntercepts);
      setLastUpdated(new Date());
      setIsLoading(false);
    }, 800);
    return () => clearTimeout(t);
  }, []);

  const decide = useCallback(
    async (id: string, decision: Exclude<DecisionStatus, "pending">, reason?: string) => {
      setIntercepts((prev) =>
        prev.map((i) =>
          i.id === id
            ? { ...i, status: decision, decidedAt: new Date().toISOString(), decisionReason: reason }
            : i
        )
      );
      setLastUpdated(new Date());
    },
    []
  );

  return { intercepts, isLoading, error: null, lastUpdated, decide, retry: () => {} };
}

// ── Firebase Realtime Database hook ─────────────────────────────────────────
function useRtdbIntercepts(): UseInterceptsReturn {
  const [intercepts, setIntercepts]   = useState<Intercept[]>([]);
  const [isLoading, setIsLoading]     = useState(true);
  const [error, setError]             = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [retryKey, setRetryKey]       = useState(0);

  useEffect(() => {
    setIsLoading(true);
    setError(null);

    const interceptsRef = ref(rtdb, "intercepts");

    onValue(
      interceptsRef,
      (snapshot) => {
        const raw = snapshot.val() as Record<string, Record<string, unknown>> | null;
        if (!raw) {
          setIntercepts([]);
        } else {
          const mapped = Object.entries(raw)
            .map(([id, data]) => rtdbDocToIntercept(id, data))
            .sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());
          setIntercepts(mapped);
        }
        setLastUpdated(new Date());
        setIsLoading(false);
      },
      (err) => {
        setError(err.message);
        setIsLoading(false);
      }
    );

    return () => off(interceptsRef);
  }, [retryKey]);

  const decide = useCallback(
    async (id: string, decision: Exclude<DecisionStatus, "pending">, reason?: string) => {
      const verdict   = decision === "approved" ? "approve" : "deny";
      const decidedAt = new Date().toISOString();

      // Optimistic update
      setIntercepts((prev) =>
        prev.map((i) =>
          i.id === id
            ? { ...i, status: decision, decidedAt, decisionReason: reason }
            : i
        )
      );
      setLastUpdated(new Date());

      // Write decision directly to RTDB so it persists across refreshes
      await update(ref(rtdb, `intercepts/${id}`), {
        verdict,
        status:          "decided",
        user_selected:   verdict,
        decision_reason: reason ?? "",
        decided_at:      Date.now(),
      });

      // Also notify backend REST API (best-effort — may 404 until deployed)
      patchDecision(id, verdict, reason).catch(() => {});
    },
    []
  );

  return {
    intercepts,
    isLoading,
    error,
    lastUpdated,
    decide,
    retry: () => setRetryKey((k) => k + 1),
  };
}

// ── Dispatcher: RTDB > REST API > Mock ───────────────────────────────────────
// Rules-of-hooks: all three must always be called; we select after.
export function useIntercepts(): UseInterceptsReturn {
  const api  = useApiIntercepts();
  const rtdb = useRtdbIntercepts();
  const mock = useMockIntercepts();

  if (FIREBASE_CONFIGURED) return rtdb;
  if (API_CONFIGURED)      return api;
  return mock;
}
