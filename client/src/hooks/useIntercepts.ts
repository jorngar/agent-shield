import { useState, useEffect, useCallback } from "react";
import type { Intercept, DecisionStatus } from "@/lib/types";
import { mockIntercepts } from "@/lib/mock-data";

const POLL_INTERVAL_MS = 10_000;

interface UseInterceptsReturn {
  intercepts: Intercept[];
  isLoading: boolean;
  error: string | null;
  lastUpdated: Date | null;
  decide: (id: string, decision: Exclude<DecisionStatus, "pending">) => void;
  retry: () => void;
}

export function useIntercepts(): UseInterceptsReturn {
  const [intercepts, setIntercepts] = useState<Intercept[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const fetchIntercepts = useCallback(async (showLoadingSpinner = false) => {
    if (showLoadingSpinner) setIsLoading(true);
    setError(null);

    try {
      // Simulated network delay — swap body for real fetch when backend is ready:
      // const res = await fetch("/api/intercepts");
      // if (!res.ok) throw new Error(`Server error ${res.status}`);
      // const data: Intercept[] = await res.json();
      await new Promise((r) => setTimeout(r, 900));
      const data = mockIntercepts;

      setIntercepts((prev) => {
        // Preserve any local decisions made during this session
        return data.map((incoming) => {
          const existing = prev.find((p) => p.id === incoming.id);
          if (existing && existing.status !== "pending") return existing;
          return incoming;
        });
      });
      setLastUpdated(new Date());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch intercepts");
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Initial load
  useEffect(() => {
    fetchIntercepts(true);
  }, [fetchIntercepts]);

  // Polling
  useEffect(() => {
    const interval = setInterval(() => fetchIntercepts(false), POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [fetchIntercepts]);

  const decide = useCallback(
    (id: string, decision: Exclude<DecisionStatus, "pending">) => {
      setIntercepts((prev) =>
        prev.map((i) =>
          i.id === id
            ? { ...i, status: decision, decidedAt: new Date().toISOString() }
            : i
        )
      );
    },
    []
  );

  return {
    intercepts,
    isLoading,
    error,
    lastUpdated,
    decide,
    retry: () => fetchIntercepts(true),
  };
}
