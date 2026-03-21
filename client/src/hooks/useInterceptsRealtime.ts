import { useState, useEffect, useCallback } from "react";
import {
  collection,
  onSnapshot,
  doc,
  updateDoc,
  query,
  orderBy,
  Timestamp,
} from "firebase/firestore";
import { db } from "@/lib/firebase";
import type { Intercept, DecisionStatus } from "@/lib/types";
import { mockIntercepts } from "@/lib/mock-data";
import { useApiIntercepts } from "./useApiIntercepts";

export interface UseInterceptsReturn {
  intercepts: Intercept[];
  isLoading: boolean;
  error: string | null;
  lastUpdated: Date | null;
  decide: (id: string, decision: Exclude<DecisionStatus, "pending">) => Promise<void>;
  retry: () => void;
}

// Priority: REST API > Firestore > Mock
const API_CONFIGURED      = Boolean(import.meta.env.VITE_API_URL);
const FIREBASE_CONFIGURED = Boolean(import.meta.env.VITE_FIREBASE_PROJECT_ID);

// ── Firestore path ──────────────────────────────────────────────────────────
const interceptsRef = () =>
  query(collection(db, "intercepts"), orderBy("timestamp", "desc"));

function normaliseTimestamp(value: unknown): string {
  if (value instanceof Timestamp) return value.toDate().toISOString();
  if (typeof value === "string") return value;
  return new Date().toISOString();
}

function docToIntercept(id: string, data: Record<string, unknown>): Intercept {
  return {
    id,
    toolName:     String(data.toolName ?? ""),
    status:       (data.status as Intercept["status"]) ?? "pending",
    riskLevel:    (data.riskLevel as Intercept["riskLevel"]) ?? "low",
    category:     String(data.category ?? ""),
    confidence:   Number(data.confidence ?? 0),
    reason:       String(data.reason ?? ""),
    timestamp:    normaliseTimestamp(data.timestamp),
    decidedAt:    data.decidedAt ? normaliseTimestamp(data.decidedAt) : undefined,
    arguments:    (data.arguments as Record<string, unknown>) ?? {},
    matchedRules: (data.matchedRules as string[]) ?? [],
  };
}

// ── Mock fallback ───────────────────────────────────────────────────────────
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
    async (id: string, decision: Exclude<DecisionStatus, "pending">) => {
      setIntercepts((prev) =>
        prev.map((i) =>
          i.id === id
            ? { ...i, status: decision, decidedAt: new Date().toISOString() }
            : i
        )
      );
      setLastUpdated(new Date());
    },
    []
  );

  return { intercepts, isLoading, error: null, lastUpdated, decide, retry: () => {} };
}

// ── Firestore realtime hook ─────────────────────────────────────────────────
function useFirestoreIntercepts(): UseInterceptsReturn {
  const [intercepts, setIntercepts]   = useState<Intercept[]>([]);
  const [isLoading, setIsLoading]     = useState(true);
  const [error, setError]             = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [retryKey, setRetryKey]       = useState(0);

  useEffect(() => {
    setIsLoading(true);
    setError(null);
    const unsubscribe = onSnapshot(
      interceptsRef(),
      (snapshot) => {
        setIntercepts(
          snapshot.docs.map((d) =>
            docToIntercept(d.id, d.data() as Record<string, unknown>)
          )
        );
        setLastUpdated(new Date());
        setIsLoading(false);
      },
      (err) => {
        setError(err.message);
        setIsLoading(false);
      }
    );
    return () => unsubscribe();
  }, [retryKey]);

  const decide = useCallback(
    async (id: string, decision: Exclude<DecisionStatus, "pending">) => {
      await updateDoc(doc(db, "intercepts", id), {
        status: decision,
        decidedAt: Timestamp.now(),
      });
      setLastUpdated(new Date());
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

// ── Dispatcher: API > Firebase > Mock ──────────────────────────────────────
// Rules-of-hooks: all three must always be called; we select after.
export function useIntercepts(): UseInterceptsReturn {
  const api      = useApiIntercepts();
  const firestore = useFirestoreIntercepts();
  const mock     = useMockIntercepts();

  if (API_CONFIGURED)      return api;
  if (FIREBASE_CONFIGURED) return firestore;
  return mock;
}
