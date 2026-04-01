import { useState } from "react";
import type { Intercept, RiskLevel } from "@/lib/types";
import { ConfidenceBar } from "./ConfidenceBar";

const riskLabel: Record<RiskLevel, string> = {
  high:   "HIGH",
  medium: "MEDIUM",
  low:    "LOW",
};

const riskText: Record<RiskLevel, string> = {
  high:   "text-risk-high",
  medium: "text-risk-medium",
  low:    "text-risk-low",
};

const riskDot: Record<RiskLevel, string> = {
  high:   "bg-risk-high",
  medium: "bg-risk-medium",
  low:    "bg-risk-low",
};

const riskBorder: Record<RiskLevel, string> = {
  high:   "border-risk-high/20",
  medium: "border-risk-medium/20",
  low:    "border-risk-low/20",
};

const riskBg: Record<RiskLevel, string> = {
  high:   "bg-risk-high/5",
  medium: "bg-risk-medium/5",
  low:    "bg-risk-low/5",
};

const riskGlow: Record<RiskLevel, string> = {
  high:   "animate-risk-glow-red",
  medium: "animate-risk-glow-amb",
  low:    "",
};

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    month: "short", day: "numeric",
    hour: "2-digit", minute: "2-digit", second: "2-digit",
  });
}

function ConsoleLine({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground/60">
        {label}
      </span>
      <div>{children}</div>
    </div>
  );
}

// ── Empty state ────────────────────────────────────────────────────────────
function EmptyDecision() {
  return (
    <div className="flex flex-1 flex-col items-center justify-center p-5">
      <div className="w-full rounded-lg border border-border/60 bg-card p-5 text-center shadow-sm">
        <div className="mx-auto mb-4 flex h-11 w-11 items-center justify-center rounded-xl border border-primary/20 bg-primary/10">
          <svg
            className="h-5 w-5 text-primary"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth={1.8}
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <circle cx="12" cy="12" r="10" />
            <path d="M12 8v4l2 2" />
          </svg>
        </div>
        <p className="font-mono text-sm font-semibold text-foreground">
          Awaiting selection
        </p>
        <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">
          Select a pending call from the stream to review and approve or deny it.
        </p>
        <div className="mt-4 flex items-center justify-center gap-1.5 font-mono text-[10px] text-muted-foreground/70">
          <span className="animate-cursor">_</span>
          <span>no call selected</span>
        </div>
      </div>
    </div>
  );
}

// ── Main ───────────────────────────────────────────────────────────────────
interface DecisionPanelProps {
  intercept: Intercept | null;
  onApprove: (id: string, reason: string) => void;
  onDeny: (id: string, reason: string) => void;
}

export function DecisionPanel({ intercept, onApprove, onDeny }: DecisionPanelProps) {
  const [pendingAction, setPendingAction] = useState<"approved" | "denied" | null>(null);
  const [reasonInput, setReasonInput]     = useState("");

  function handleActionClick(action: "approved" | "denied") {
    setPendingAction(action);
    setReasonInput("");
  }

  function handleConfirm() {
    if (!intercept || !pendingAction) return;
    if (pendingAction === "approved") onApprove(intercept.id, reasonInput);
    else onDeny(intercept.id, reasonInput);
    setPendingAction(null);
    setReasonInput("");
  }

  function handleCancel() {
    setPendingAction(null);
    setReasonInput("");
  }

  if (!intercept) return (
    <div className="flex h-full flex-col">
      <div className="border-b border-border px-4 py-3">
        <span className="font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground/60">
          Decision Panel
        </span>
      </div>
      <EmptyDecision />
    </div>
  );

  const { id, riskLevel, category, confidence, reason, status, decidedAt, decisionReason } = intercept;

  return (
    <div className="flex h-full flex-col overflow-hidden" key={id}>

      {/* ── Risk level header ──────────────────────────────────────────── */}
      <div className={`border-b animate-slide-up-fade ${riskBorder[riskLevel]} ${riskBg[riskLevel]} px-4 py-4`}>
        <span className="font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground/70">
          Risk Level
        </span>
        <div className="mt-2 flex items-center gap-2.5">
          <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${riskDot[riskLevel]} ${riskGlow[riskLevel]}`} />
          <span className={`font-mono text-2xl font-bold tracking-wide ${riskText[riskLevel]}`}>
            {riskLabel[riskLevel]}
          </span>
        </div>
        <div className="mt-3">
          <ConfidenceBar value={confidence} riskLevel={riskLevel} />
        </div>
      </div>

      {/* ── Scrollable details ─────────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto divide-y divide-border/40">

        {/* Category */}
        <div className="px-4 py-3.5">
          <ConsoleLine label="Category">
            <span className="font-mono text-sm text-foreground">{category}</span>
          </ConsoleLine>
        </div>

        {/* Assessment */}
        <div className="px-4 py-3.5">
          <ConsoleLine label="Assessment">
            <p className="text-xs leading-relaxed text-foreground/70">{reason}</p>
          </ConsoleLine>
        </div>

        {/* Matched rules count */}
        <div className="px-4 py-3.5">
          <ConsoleLine label="Rules Triggered">
            <span className="font-mono text-sm text-foreground">
              {intercept.matchedRules.length}
              <span className="ml-2 text-xs text-muted-foreground">
                — see inspector
              </span>
            </span>
          </ConsoleLine>
        </div>

      </div>

      {/* ── Decision footer ────────────────────────────────────────────── */}
      <div className="shrink-0 border-t border-border">

        {status === "pending" && !pendingAction && (
          <div className="p-4">
            <p className="mb-3 font-mono text-[10px] text-muted-foreground/60">
              // AWAITING DECISION — {id}
            </p>
            <div className="flex flex-col gap-2">
              <button
                onClick={() => handleActionClick("denied")}
                className="w-full rounded border border-risk-high bg-risk-high/10 px-4 py-2.5 font-mono text-xs font-bold uppercase tracking-widest text-risk-high transition-all duration-150 hover:bg-risk-high hover:text-risk-high-foreground active:scale-[0.98]"
              >
                ✕  Deny
              </button>
              <button
                onClick={() => handleActionClick("approved")}
                className="w-full rounded border border-risk-low/40 bg-transparent px-4 py-2.5 font-mono text-xs font-semibold uppercase tracking-widest text-risk-low/80 transition-all duration-150 hover:border-risk-low hover:bg-risk-low/10 hover:text-risk-low active:scale-[0.98]"
              >
                ✓  Approve
              </button>
            </div>
          </div>
        )}

        {status === "pending" && pendingAction && (
          <div className="p-4">
            <p className={`mb-2 font-mono text-[10px] font-bold uppercase tracking-widest ${pendingAction === "approved" ? "text-risk-low" : "text-risk-high"}`}>
              {pendingAction === "approved" ? "✓ Approving" : "✕ Denying"} — add reason
            </p>
            <textarea
              value={reasonInput}
              onChange={(e) => setReasonInput(e.target.value)}
              placeholder="Reason (optional)..."
              rows={3}
              className="w-full resize-none rounded border border-border/60 bg-card px-3 py-2 font-mono text-xs text-foreground placeholder:text-muted-foreground/40 focus:border-primary/40 focus:outline-none"
            />
            <div className="mt-2 flex gap-2">
              <button
                onClick={handleCancel}
                className="flex-1 rounded border border-border/60 px-3 py-2 font-mono text-xs text-muted-foreground/70 hover:border-border hover:text-foreground transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleConfirm}
                className={`flex-1 rounded border px-3 py-2 font-mono text-xs font-bold uppercase tracking-widest transition-all active:scale-[0.98]
                  ${pendingAction === "approved"
                    ? "border-risk-low bg-risk-low/10 text-risk-low hover:bg-risk-low hover:text-white"
                    : "border-risk-high bg-risk-high/10 text-risk-high hover:bg-risk-high hover:text-white"
                  }`}
              >
                Confirm
              </button>
            </div>
          </div>
        )}

        {status !== "pending" && (
          <div className={`px-4 py-3 font-mono ${status === "approved" ? "bg-risk-low/10 text-risk-low" : "bg-risk-high/10 text-risk-high"}`}>
            <div className="text-center text-xs font-bold uppercase tracking-widest">
              {status === "approved" ? "✓" : "✕"}  {status}
            </div>
            {decidedAt && (
              <div className="mt-0.5 text-center text-[10px] font-normal tracking-normal opacity-60">
                {formatDateTime(decidedAt)}
              </div>
            )}
            {decisionReason && !/localhost|Client Error|Not Found for url|Error:/i.test(decisionReason) && (
              <p className="mt-2 border-t border-current/20 pt-2 text-[10px] font-normal leading-relaxed tracking-normal opacity-70">
                {decisionReason}
              </p>
            )}
          </div>
        )}

      </div>
    </div>
  );
}
