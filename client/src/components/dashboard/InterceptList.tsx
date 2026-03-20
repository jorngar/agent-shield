import { useState, useMemo } from "react";
import type { Intercept, DecisionStatus } from "@/lib/types";
import { InterceptCard } from "./InterceptCard";

type StatusFilter = "all" | DecisionStatus;

// ── Skeleton ───────────────────────────────────────────────────────────────
function SkeletonRow() {
  return (
    <div className="animate-pulse border-l-2 border-l-muted px-3 py-2">
      <div className="flex items-center gap-2">
        <div className="h-1.5 w-1.5 rounded-full bg-muted/60" />
        <div className="h-2.5 w-24 rounded bg-muted/50" />
        <div className="ml-auto h-2 w-10 rounded bg-muted/40" />
      </div>
      <div className="mt-1 flex items-center gap-2 pl-3.5">
        <div className="h-2 w-20 rounded bg-muted/35" />
        <div className="ml-auto h-3.5 w-10 rounded-full bg-muted/30" />
      </div>
    </div>
  );
}

// ── Error ──────────────────────────────────────────────────────────────────
function ErrorBanner({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="mx-3 my-2 rounded border border-risk-high/20 bg-risk-high/5 p-2.5">
      <p className="font-mono text-[10px] font-bold uppercase tracking-widest text-risk-high">
        Connection Error
      </p>
      <p className="mt-0.5 truncate font-mono text-[10px] text-risk-high/60">{message}</p>
      <button
        onClick={onRetry}
        className="mt-1.5 font-mono text-[10px] font-bold text-risk-high underline underline-offset-2"
      >
        retry
      </button>
    </div>
  );
}

// ── Empty ──────────────────────────────────────────────────────────────────
function EmptyState({ filtered }: { filtered: boolean }) {
  return (
    <div className="flex flex-col items-center justify-center py-12 px-4 text-center">
      <p className="font-mono text-[11px] text-muted-foreground/60">
        {filtered ? "// no matches" : "// stream empty"}
      </p>
      <p className="mt-1 font-mono text-[10px] text-muted-foreground/45">
        {filtered ? "adjust filter" : "awaiting agent activity"}
      </p>
    </div>
  );
}

// ── Main ───────────────────────────────────────────────────────────────────
interface InterceptListProps {
  intercepts: Intercept[];
  selectedId: string | null;
  isLoading: boolean;
  error: string | null;
  onSelect: (id: string) => void;
  onRetry: () => void;
}

export function InterceptList({
  intercepts,
  selectedId,
  isLoading,
  error,
  onSelect,
  onRetry,
}: InterceptListProps) {
  const [search, setSearch]       = useState("");
  const [statusFilter, setStatus] = useState<StatusFilter>("all");

  const filtered = useMemo(() => {
    return intercepts.filter((i) => {
      if (statusFilter !== "all" && i.status !== statusFilter) return false;
      if (search && !i.toolName.toLowerCase().includes(search.toLowerCase()) &&
          !i.category.toLowerCase().includes(search.toLowerCase())) return false;
      return true;
    });
  }, [intercepts, statusFilter, search]);

  const pending = intercepts.filter((i) => i.status === "pending").length;

  return (
    <div className="flex h-full flex-col">

      {/* ── Panel header ────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between border-b border-border px-3 py-2.5">
        <span className="font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground/70">
          Intercept Stream
        </span>
        <div className="flex items-center gap-2">
          {pending > 0 && (
            <span className="font-mono text-[10px] font-bold text-risk-medium">
              {pending} pending
            </span>
          )}
          <span className="font-mono text-[10px] text-muted-foreground/55">
            [{filtered.length}]
          </span>
        </div>
      </div>

      {/* ── Search ──────────────────────────────────────────────────────── */}
      <div className="border-b border-border/60 px-3 py-2">
        <div className="flex items-center gap-1.5 font-mono text-xs text-muted-foreground/70">
          <span className="shrink-0 text-primary/70">&gt;</span>
          <input
            type="text"
            placeholder="filter…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="flex-1 bg-transparent font-mono text-xs text-foreground placeholder:text-muted-foreground/45 focus:outline-none"
          />
          {search && (
            <button
              onClick={() => setSearch("")}
              className="shrink-0 font-mono text-[10px] text-muted-foreground/55 hover:text-muted-foreground"
            >
              ✕
            </button>
          )}
        </div>
      </div>

      {/* ── Status filter ───────────────────────────────────────────────── */}
      <div className="flex items-center gap-0 border-b border-border/60">
        {(["all", "pending", "approved", "denied"] as StatusFilter[]).map((s) => (
          <button
            key={s}
            onClick={() => setStatus(s)}
            className={`
              flex-1 border-r border-border/40 last:border-r-0 py-1.5
              font-mono text-[10px] uppercase tracking-wider transition-colors
              ${statusFilter === s
                ? "bg-primary/10 text-primary"
                : "text-muted-foreground/55 hover:text-muted-foreground"
              }
            `}
          >
            {s === "all" ? "all" : s.slice(0, 4)}
          </button>
        ))}
      </div>

      {/* ── Error ───────────────────────────────────────────────────────── */}
      {error && <ErrorBanner message={error} onRetry={onRetry} />}

      {/* ── Stream ──────────────────────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto">
        {isLoading ? (
          <div className="divide-y divide-border/30">
            {Array.from({ length: 6 }).map((_, i) => <SkeletonRow key={i} />)}
          </div>
        ) : filtered.length === 0 ? (
          <EmptyState filtered={intercepts.length > 0} />
        ) : (
          <div className="divide-y divide-border/30">
            {filtered.map((intercept) => (
              <InterceptCard
                key={intercept.id}
                intercept={intercept}
                isSelected={selectedId === intercept.id}
                onClick={() => onSelect(intercept.id)}
              />
            ))}
          </div>
        )}
      </div>

      {/* ── Footer ──────────────────────────────────────────────────────── */}
      {!isLoading && (
        <div className="border-t border-border/40 px-3 py-1.5">
          <span className="font-mono text-[10px] text-muted-foreground/55">
            {filtered.length}/{intercepts.length} events
          </span>
        </div>
      )}
    </div>
  );
}
