import { useState, useEffect, useRef, useCallback } from "react";
import type { Intercept, DecisionStatus } from "@/lib/types";
import { fetchAuditLog, patchDecision, mapApiIntercept } from "@/lib/api";

const POLL_MS = 2_000;

interface UseInterceptsReturn {
  intercepts: Intercept[];
  isLoading: boolean;
  error: string | null;
  lastUpdated: Date | null;
  decide: (id: string, decision: Exclude<DecisionStatus, "pending">) => Promise<void>;
  retry: () => void;
}

export function useApiIntercepts(): UseInterceptsReturn {
  const [intercepts, setIntercepts]   = useState<Intercept[]>([]);
  const [isLoading, setIsLoading]     = useState(true);
  const [error, setError]             = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const timerRef    = useRef<ReturnType<typeof setTimeout> | null>(null);
  const retryKeyRef = useRef(0);

  const poll = useCallback(async () => {
    try {
      const data = await fetchAuditLog(100);
      setIntercepts(data.map(mapApiIntercept));
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
    async (id: string, decision: Exclude<DecisionStatus, "pending">) => {
      const verdict = decision === "approved" ? "approve" : "deny";

      // Optimistic update immediately
      setIntercepts((prev) =>
        prev.map((i) =>
          i.id === id
            ? { ...i, status: decision, decidedAt: new Date().toISOString() }
            : i
        )
      );
      setLastUpdated(new Date());

      try {
        await patchDecision(Number(id), verdict);
      } catch {
        // PATCH /audit/:id/decision not yet built — optimistic update stands
        // until next poll corrects it if needed
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
