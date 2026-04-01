export interface ThreatLineData {
  readonly type: string;
  readonly text: string;
}

export interface ThreatLogProps {
  lines: readonly ThreatLineData[];
  visibleCount: number;
  blockedLine?: ThreatLineData;
  showBlocked?: boolean;
}

const THREAT_STYLES: Record<string, string> = {
  warn: "text-amber",
  alert: "text-danger font-semibold",
  file: "text-muted-foreground",
  blocked: "text-mint font-semibold",
};

export function ThreatLog({
  lines,
  visibleCount,
  blockedLine,
  showBlocked = false,
}: ThreatLogProps) {
  return (
    <div className="animate-slide-up-fade rounded-xl border border-danger/30 bg-card/90 backdrop-blur-sm shadow-xl overflow-hidden">
      <div className="flex items-center gap-2 px-4 py-2 border-b border-danger/20 bg-danger/5">
        <div className="w-2 h-2 rounded-full bg-danger animate-pulse" />
        <span className="text-xs text-danger/80 font-mono font-semibold tracking-wide">
          THREAT LOG
        </span>
      </div>

      <div className="p-4 font-mono text-xs leading-relaxed space-y-1.5">
        {lines.slice(0, visibleCount).map((line, i) => (
          <div
            key={i}
            className={`animate-slide-up-fade ${THREAT_STYLES[line.type] ?? "text-muted-foreground"}`}
          >
            {line.text}
          </div>
        ))}

        {showBlocked && blockedLine && (
          <div className="animate-slide-up-fade text-mint font-semibold">
            {blockedLine.text}
          </div>
        )}

        {visibleCount > 0 && !showBlocked && (
          <span className="inline-block w-[2px] h-3 bg-danger ml-[1px] align-middle animate-cursor" />
        )}
      </div>
    </div>
  );
}
