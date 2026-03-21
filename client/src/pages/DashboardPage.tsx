import { useState } from "react";
import { useIntercepts } from "@/hooks/useInterceptsRealtime";
import { Header } from "@/components/dashboard/Header";
import { StatsBar } from "@/components/dashboard/StatsBar";
import { InterceptList } from "@/components/dashboard/InterceptList";
import { InspectorPanel } from "@/components/dashboard/InspectorPanel";
import { DecisionPanel } from "@/components/dashboard/DecisionPanel";
import { DashboardTour } from "@/components/dashboard/DashboardTour";
import { seedFirestore } from "@/lib/seed";

const IS_DEV = import.meta.env.DEV;
const TOUR_KEY = "agentshield_tour_done";

export default function DashboardPage() {
  const { intercepts, isLoading, error, lastUpdated, decide, retry } = useIntercepts();
  const [selectedId, setSelectedId]   = useState<string | null>(null);
  const [mobileView, setMobileView]   = useState<"list" | "detail">("list");
  const [tourActive, setTourActive]   = useState(() => !localStorage.getItem(TOUR_KEY));

  const selected = intercepts.find((i) => i.id === selectedId) ?? null;

  function handleSelect(id: string) {
    setSelectedId(id);
    setMobileView("detail");
  }

  function handleTourFinish() {
    localStorage.setItem(TOUR_KEY, "1");
    setTourActive(false);
  }

  return (
    <div className="flex h-dvh flex-col bg-background text-foreground">

      <DashboardTour run={tourActive} onFinish={handleTourFinish} />

      <div id="tour-header">
        <Header
          intercepts={intercepts}
          lastUpdated={lastUpdated}
          isLoading={isLoading}
          selectedToolName={selected?.toolName}
          showBackButton={mobileView === "detail"}
          onShowList={() => setMobileView("list")}
        />
      </div>

      <div id="tour-stats">
        <StatsBar intercepts={intercepts} isLoading={isLoading} />
      </div>

      {/* Dev seed bar */}
      {IS_DEV && (
        <div className="flex items-center gap-3 border-b border-border/50 bg-card/20 px-5 py-1">
          <span className="font-mono text-[10px] font-bold text-risk-medium">DEV</span>
          <span className="font-mono text-[10px] text-muted-foreground/40">agentshield-a8848</span>
          <button
            onClick={() => seedFirestore()}
            className="ml-auto rounded border border-border/50 px-2 py-0.5 font-mono text-[10px] text-muted-foreground/60 hover:border-primary/40 hover:text-primary"
          >
            seed firestore
          </button>
          <button
            onClick={() => { localStorage.removeItem(TOUR_KEY); setTourActive(true); }}
            className="rounded border border-border/50 px-2 py-0.5 font-mono text-[10px] text-muted-foreground/60 hover:border-primary/40 hover:text-primary"
          >
            replay tour
          </button>
        </div>
      )}

      <main className="flex flex-1 overflow-hidden">

        {/* ════════════════════════════════════════════════════════════════
            DESKTOP (lg+): 3-column layout — stream | inspector | decision
        ════════════════════════════════════════════════════════════════ */}
        <div className="hidden flex-1 overflow-hidden lg:flex">

          {/* Left: intercept stream */}
          <div id="tour-intercept-list" className="w-64 shrink-0 border-r border-border xl:w-72">
            <InterceptList
              intercepts={intercepts}
              selectedId={selectedId}
              isLoading={isLoading}
              error={error}
              onSelect={(id) => setSelectedId(id)}
              onRetry={retry}
            />
          </div>

          {/* Center: inspector */}
          <div id="tour-inspector" className="flex flex-1 flex-col overflow-hidden border-r border-border">
            <InspectorPanel intercept={selected} />
          </div>

          {/* Right: decision panel */}
          <div id="tour-decision" className="w-64 shrink-0 xl:w-72">
            <DecisionPanel
              intercept={selected}
              onApprove={(id, reason) => decide(id, "approved", reason)}
              onDeny={(id, reason) => decide(id, "denied", reason)}
            />
          </div>

        </div>

        {/* ════════════════════════════════════════════════════════════════
            MOBILE (< lg): list view
        ════════════════════════════════════════════════════════════════ */}
        <div className={`flex flex-1 flex-col overflow-hidden lg:hidden ${mobileView === "list" ? "" : "hidden"}`}>
          <InterceptList
            intercepts={intercepts}
            selectedId={selectedId}
            isLoading={isLoading}
            error={error}
            onSelect={handleSelect}
            onRetry={retry}
          />
        </div>

        {/* ════════════════════════════════════════════════════════════════
            MOBILE (< lg): detail view — inspector + decision at bottom
        ════════════════════════════════════════════════════════════════ */}
        <div className={`flex flex-1 flex-col overflow-hidden lg:hidden ${mobileView === "detail" ? "" : "hidden"}`}>

          {/* Inspector — scrollable */}
          <div className="flex-1 overflow-y-auto">
            <InspectorPanel intercept={selected} />
          </div>

          {/* Decision — sticky at bottom */}
          {selected?.status === "pending" && (
            <div className="shrink-0 border-t border-border bg-card/50 p-3">
              <p className="mb-2 font-mono text-[10px] text-muted-foreground/40">
                // awaiting decision — {selected.id}
              </p>
              <div className="flex gap-2">
                <button
                  onClick={() => decide(selected.id, "denied", "")}
                  className="flex-1 rounded border border-risk-high bg-risk-high/10 px-4 py-2.5 font-mono text-xs font-bold uppercase tracking-widest text-risk-high hover:bg-risk-high hover:text-white active:scale-[0.98] transition-all"
                >
                  ✕ Deny
                </button>
                <button
                  onClick={() => decide(selected.id, "approved", "")}
                  className="flex-1 rounded border border-risk-low/40 px-4 py-2.5 font-mono text-xs font-semibold uppercase tracking-widest text-risk-low/80 hover:border-risk-low hover:bg-risk-low/10 hover:text-risk-low active:scale-[0.98] transition-all"
                >
                  ✓ Approve
                </button>
              </div>
            </div>
          )}

          {selected && selected.status !== "pending" && (
            <div className={`shrink-0 border-t border-border px-4 py-2.5 text-center font-mono text-xs font-bold uppercase tracking-widest
              ${selected.status === "approved"
                ? "bg-risk-low/10 text-risk-low"
                : "bg-risk-high/10 text-risk-high"
              }`}
            >
              {selected.status === "approved" ? "✓" : "✕"}  {selected.status}
            </div>
          )}

        </div>

      </main>
    </div>
  );
}
