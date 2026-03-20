import type { Intercept } from "@/lib/types";
import { RiskBadge } from "./RiskBadge";
import { StatusBadge } from "./StatusBadge";
import { ConfidenceBar } from "./ConfidenceBar";

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    month: "short", day: "numeric",
    hour: "2-digit", minute: "2-digit", second: "2-digit",
  });
}

// ── Section header with stagger ─────────────────────────────────────────────
function Section({
  label, children, delay = 0,
}: {
  label: string;
  children: React.ReactNode;
  delay?: number;
}) {
  return (
    <div
      className="border-b border-border/40 px-5 py-4 animate-slide-up-fade"
      style={{ animationDelay: `${delay}ms`, animationFillMode: "both" }}
    >
      <div className="mb-3 flex items-center gap-3">
        <span className="font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground/40">
          {label}
        </span>
        <div className="h-px flex-1 bg-border/30" />
      </div>
      {children}
    </div>
  );
}

// ── Empty state ────────────────────────────────────────────────────────────
function EmptyInspector() {
  return (
    <div className="flex flex-1 flex-col items-center justify-center p-6">
      <div className="w-full max-w-xs rounded-lg border border-border/60 bg-card p-6 text-center shadow-sm">

        {/* Shield icon */}
        <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-xl border border-primary/20 bg-primary/10">
          <svg
            className="h-6 w-6 text-primary"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth={1.75}
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
          </svg>
        </div>

        {/* Text */}
        <p className="font-mono text-sm font-semibold text-foreground">
          No call selected
        </p>
        <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">
          Select an intercepted call from the stream on the left to inspect its payload, risk assessment, and matched rules.
        </p>

        {/* Hint */}
        <div className="mt-4 flex items-center justify-center gap-1.5 font-mono text-[10px] text-muted-foreground/50">
          <span className="animate-cursor">_</span>
          <span>awaiting selection</span>
        </div>
      </div>
    </div>
  );
}

// ── Main ───────────────────────────────────────────────────────────────────
interface InspectorPanelProps {
  intercept: Intercept | null;
}

export function InspectorPanel({ intercept }: InspectorPanelProps) {
  if (!intercept) return (
    <div className="flex h-full flex-col">
      <div className="border-b border-border px-5 py-3">
        <span className="font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground/40">
          Inspector
        </span>
      </div>
      <EmptyInspector />
    </div>
  );

  const {
    id, toolName, status, riskLevel, category, confidence,
    reason, timestamp, decidedAt, arguments: args, matchedRules,
  } = intercept;

  return (
    <div className="flex h-full flex-col overflow-hidden" key={id}>

      {/* ── Call header ───────────────────────────────────────────────── */}
      <div className="shrink-0 border-b border-border bg-card px-5 py-4 animate-slide-up-fade">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground/40">
              Intercepted Call
            </div>
            <div className="mt-1 font-mono text-xl font-bold text-primary">
              {toolName}
            </div>
          </div>
          <StatusBadge status={status} />
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[10px] text-muted-foreground/50">
          <span>{id}</span>
          <span className="text-muted-foreground/25">·</span>
          <span>{category}</span>
          <span className="text-muted-foreground/25">·</span>
          <span>{formatDateTime(timestamp)}</span>
        </div>
      </div>

      {/* ── Scrollable body ───────────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto">

        {/* Risk */}
        <Section label="Risk Assessment" delay={60}>
          <div className="flex items-center gap-4">
            <RiskBadge level={riskLevel} />
            <div className="flex-1">
              <ConfidenceBar value={confidence} riskLevel={riskLevel} />
            </div>
          </div>
        </Section>

        {/* Reason */}
        <Section label="Assessment" delay={120}>
          <p className="text-sm leading-relaxed text-foreground/80">{reason}</p>
        </Section>

        {/* Matched rules */}
        <Section label={`Matched Rules (${matchedRules.length})`} delay={180}>
          <div className="flex flex-wrap gap-1.5">
            {matchedRules.map((rule, i) => (
              <span
                key={rule}
                className="rounded border border-primary/20 bg-primary/5 px-2 py-0.5 font-mono text-[11px] text-primary/80 animate-slide-up-fade"
                style={{ animationDelay: `${180 + i * 40}ms`, animationFillMode: "both" }}
              >
                {rule}
              </span>
            ))}
          </div>
        </Section>

        {/* Arguments — GitHub-dark code block */}
        <Section label="Arguments" delay={240}>
          <div className="overflow-hidden rounded-md border border-[#30363d]">
            <div className="flex items-center border-b border-[#21262d] bg-[#161b22] px-3 py-1.5">
              <span className="font-mono text-[10px] text-[#8b949e]">json</span>
            </div>
            <pre className="overflow-x-auto bg-[#0d1117] p-4 font-mono text-[11px] leading-relaxed text-[#e6edf3]">
              {JSON.stringify(args, null, 2)}
            </pre>
          </div>
        </Section>

        {/* Decision record — only if resolved */}
        {decidedAt && (
          <Section label="Decision Record" delay={300}>
            <div className="flex items-center justify-between gap-4">
              <div className="flex items-center gap-2">
                <StatusBadge status={status} />
                <span className="font-mono text-xs text-muted-foreground/60">by reviewer</span>
              </div>
              <span className="font-mono text-[11px] text-muted-foreground/60">
                {formatDateTime(decidedAt)}
              </span>
            </div>
          </Section>
        )}

        {/* Bottom padding */}
        <div className="h-6" />
      </div>
    </div>
  );
}
