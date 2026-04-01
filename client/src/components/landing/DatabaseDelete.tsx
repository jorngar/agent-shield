export interface DatabaseDeleteProps {
  /** 0-1 progress of the deletion bar */
  deleteProgress: number;
  /** Whether the BLOCKED line has appeared */
  blocked: boolean;
}

const DB_TABLES = [
  { name: "users", rows: "1,284,301" },
  { name: "transactions", rows: "8,492,118" },
  { name: "credentials", rows: "312,847" },
  { name: "audit_logs", rows: "24,001,583" },
];

export function DatabaseDelete({ deleteProgress, blocked }: DatabaseDeleteProps) {
  const barPercent = Math.min(blocked ? 99 : 100, Math.round(deleteProgress * 100));
  const showBar = deleteProgress > 0;

  return (
    <div className="rounded-xl border border-danger/40 bg-card/90 backdrop-blur-sm shadow-2xl shadow-danger/10 overflow-hidden">
      {/* Title bar */}
      <div className="flex items-center gap-2 px-4 py-3 border-b border-danger/20 bg-danger/5">
        <div className="w-3 h-3 rounded-full bg-danger/80" />
        <div className="w-3 h-3 rounded-full bg-amber/80" />
        <div className="w-3 h-3 rounded-full bg-mint/80" />
        <span className="ml-2 text-xs text-danger/80 font-mono font-semibold tracking-wide">
          psql — production database
        </span>
      </div>

      <div className="p-5 font-mono text-xs space-y-4">
        {/* SQL command */}
        <div>
          <span className="text-muted-foreground">postgres=#</span>{" "}
          <span className="text-danger font-semibold">DROP DATABASE</span>{" "}
          <span className="text-foreground">production</span>
          <span className="text-danger font-semibold"> CASCADE;</span>
        </div>

        {/* Tables queued for deletion */}
        <div className="space-y-2">
          {DB_TABLES.map((table, i) => {
            const tableStart = i / DB_TABLES.length;
            const visible = deleteProgress > tableStart;
            if (!visible) return null;
            return (
              <div key={i} className="animate-slide-up-fade flex items-center justify-between text-muted-foreground">
                <span>
                  Preparing <span className="text-foreground">{table.name}</span>...
                </span>
                <span className="text-danger/70">{table.rows} rows</span>
              </div>
            );
          })}
        </div>

        {/* Main loader bar */}
        {showBar && (
          <div className="space-y-2 animate-slide-up-fade">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                {!blocked && (
                  <span className="inline-block w-2 h-2 rounded-full bg-danger animate-pulse" />
                )}
                <span className="text-danger font-semibold">
                  Ready to delete whole database
                </span>
              </div>
              <span className="text-foreground">{barPercent}%</span>
            </div>
            <div className="h-3 w-full rounded-full bg-secondary overflow-hidden">
              <div
                className={[
                  "h-full rounded-full transition-all duration-500 ease-out",
                  blocked ? "bg-mint" : "bg-danger",
                ].join(" ")}
                style={{ width: `${barPercent}%` }}
              />
            </div>

            {/* Blocked message */}
            {blocked && (
              <div className="mt-3 pt-3 border-t border-danger/20 space-y-2 animate-slide-up-fade">
                <div className="text-mint font-semibold text-sm">
                  [AGENT SHIELD] Action BLOCKED — awaiting human review
                </div>
                <div className="text-muted-foreground text-[10px]">
                  0 rows deleted — database intact — rollback complete
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
