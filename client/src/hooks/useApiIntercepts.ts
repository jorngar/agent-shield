import { useState, useEffect, useRef, useCallback } from "react";
import type { Intercept, DecisionStatus } from "@/lib/types";
import { fetchAuditLog, patchDecision, mapApiIntercept } from "@/lib/api";

const POLL_MS = 2_000;

interface UseInterceptsReturn {
  intercepts: Intercept[];
  isLoading: boolean;
  error: string | null;
  lastUpdated: Date | null;
  decide: (id: string, decision: Exclude<DecisionStatus, "pending">, reason?: string) => Promise<void>;
  retry: () => void;
}

export function useApiIntercepts(): UseInterceptsReturn {
  const [intercepts, setIntercepts]   = useState<Intercept[]>([]);
  const [isLoading, setIsLoading]     = useState(true);
  const [error, setError]             = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const timerRef       = useRef<ReturnType<typeof setTimeout> | null>(null);
  const retryKeyRef    = useRef(0);
  // Track local decisions so polls don't overwrite them
  const localDecisions = useRef<Map<string, { status: Exclude<DecisionStatus, "pending">; decidedAt: string }>>(new Map());

  const poll = useCallback(async () => {
    try {
      const data = await fetchAuditLog(100);
      setIntercepts(
        data.map(mapApiIntercept).map((intercept) => {
          const local = localDecisions.current.get(intercept.id);
          // If backend has caught up with the decision, clear the local override
          if (local && intercept.status !== "pending") {
            localDecisions.current.delete(intercept.id);
            return intercept;
          }
          // Otherwise preserve the local optimistic decision
          if (local) return { ...intercept, status: local.status, decidedAt: local.decidedAt };
          return intercept;
        })
      );
      setLastUpdated(new Date());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to reach API");
    } finally {
      setIsLoading(false);
      timerRef.current = setTimeout(poll, POLL_MS);
    }
  }, []);

  useEffect(() => {
    setIsLoading(true);
    poll();
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  // retryKeyRef changes trigger a fresh effect via retry()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [poll, retryKeyRef.current]);

  const decide = useCallback(
    async (id: string, decision: Exclude<DecisionStatus, "pending">, reason?: string) => {
      const verdict   = decision === "approved" ? "approve" : "deny";
      const decidedAt = new Date().toISOString();

      localDecisions.current.set(id, { status: decision, decidedAt });

      setIntercepts((prev) =>
        prev.map((i) => i.id === id ? { ...i, status: decision, decidedAt, decisionReason: reason } : i)
      );
      setLastUpdated(new Date());

      try {
        await patchDecision(id, verdict, reason);
      } catch {
        // Decision preserved locally until backend catches up
      }
    },
    []
  );

  const retry = useCallback(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    retryKeyRef.current += 1;
    setIsLoading(true);
    setError(null);
    poll();
  }, [poll]);

  return { intercepts, isLoading, error, lastUpdated, decide, retry };
}
