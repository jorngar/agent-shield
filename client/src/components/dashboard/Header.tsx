import type { Intercept } from "@/lib/types";

function formatTime(date: Date | null): string {
  if (!date) return "—";
  return date.toLocaleTimeString(undefined, {
    hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false,
  });
}

interface HeaderProps {
  intercepts: Intercept[];
  lastUpdated: Date | null;
  isLoading: boolean;
  selectedToolName?: string;
  showBackButton?: boolean;
  onShowList?: () => void;
}

export function Header({
  intercepts,
  lastUpdated,
  isLoading,
  selectedToolName,
  showBackButton = false,
  onShowList,
}: HeaderProps) {
  const pending = intercepts.filter((i) => i.status === "pending").length;

  return (
    <header className="flex h-11 shrink-0 items-center justify-between border-b border-border bg-card px-4 md:px-5">

      {/* ── Left: back (mobile) + brand + breadcrumb ──────────────────── */}
      <div className="flex min-w-0 items-center gap-3">
        {showBackButton && (
          <button
            onClick={onShowList}
            className="mr-1 font-mono text-[10px] text-primary/70 hover:text-primary lg:hidden"
          >
            ← stream
          </button>
        )}

        {/* Logo / name */}
        <div className="flex items-center gap-2.5">
          <img
            src="/logo.png"
            alt="AgentGuard"
            className="h-6 w-auto shrink-0 object-contain"
            onError={(e) => {
              e.currentTarget.style.display = "none";
              e.currentTarget.nextElementSibling?.removeAttribute("hidden");
            }}
          />
          <div hidden className="flex h-6 w-6 shrink-0 items-center justify-center rounded bg-primary/15">
            <svg className="h-3 w-3 text-primary" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
            </svg>
          </div>
          <span className="font-mono text-sm font-bold text-foreground">AgentGuard</span>
        </div>

        {/* Breadcrumb */}
        <div className="hidden items-center gap-1.5 font-mono text-xs sm:flex">
          <span className="text-muted-foreground/30">/</span>
          <span className="text-muted-foreground/60">intercepts</span>
          {selectedToolName && (
            <>
              <span className="text-muted-foreground/30">/</span>
              <span className="truncate font-bold text-primary/80">{selectedToolName}</span>
            </>
          )}
        </div>
      </div>

      {/* ── Right: status ─────────────────────────────────────────────── */}
      <div className="flex shrink-0 items-center gap-3 font-mono text-[11px]">

        {/* Last synced */}
        <span className="hidden text-muted-foreground/40 sm:block">
          {isLoading ? (
            <span className="animate-pulse">syncing…</span>
          ) : (
            <span>{formatTime(lastUpdated)}</span>
          )}
        </span>

        {/* Pending */}
        {pending > 0 && (
          <span className="font-bold text-risk-medium">
            {pending} pending
          </span>
        )}

        {/* Live indicator */}
        <div className="flex items-center gap-1.5 rounded border border-border/50 bg-card px-2 py-1">
          <span className="relative flex h-1.5 w-1.5">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-risk-low opacity-50" />
            <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-risk-low" />
          </span>
          <span className="text-muted-foreground/70">live</span>
        </div>

      </div>
    </header>
  );
}
