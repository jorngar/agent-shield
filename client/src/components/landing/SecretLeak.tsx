export interface SecretLeakProps {
  /** 0-1 scroll progress for this animation */
  leakProgress: number;
  /** Whether the BLOCKED line has appeared */
  blocked: boolean;
}

const LEAK_STEPS = [
  { type: "cmd", text: "Reading files..." },
  { type: "cmd", text: "Processing docker-compose.yml..." },
  { type: "alert", text: "Extracting API keys from docker-compose..." },
  { type: "danger", text: "Publishing keys to Telegram..." },
] as const;

const STEP_STYLES: Record<string, string> = {
  cmd: "text-muted-foreground",
  alert: "text-amber font-semibold",
  danger: "text-danger font-semibold",
};

export function SecretLeak({ leakProgress, blocked }: SecretLeakProps) {
  // Show steps one by one based on progress (last step excluded if blocked catches it)
  const totalSteps = LEAK_STEPS.length;
  const visibleSteps = Math.min(
    totalSteps,
    Math.floor(leakProgress * (totalSteps + 1)),
  );

  return (
    <div className="rounded-xl border border-danger/40 bg-card/90 backdrop-blur-sm shadow-2xl shadow-danger/10 overflow-hidden">
      {/* Title bar */}
      <div className="flex items-center gap-2 px-4 py-3 border-b border-danger/20 bg-danger/5">
        <div className="w-3 h-3 rounded-full bg-danger/80" />
        <div className="w-3 h-3 rounded-full bg-amber/80" />
        <div className="w-3 h-3 rounded-full bg-mint/80" />
        <span className="ml-2 text-xs text-danger/80 font-mono font-semibold tracking-wide">
          agent — secret leak detected
        </span>
      </div>

      <div className="p-5 font-mono text-xs space-y-3">
        {/* Leak steps */}
        {LEAK_STEPS.slice(0, visibleSteps).map((step, i) => (
          <div
            key={i}
            className={`animate-slide-up-fade ${STEP_STYLES[step.type]}`}
          >
            <span className="text-teal/60 mr-2">$</span>
            {step.text}
          </div>
        ))}

        {/* Fake extracted keys */}
        {visibleSteps >= 3 && (
          <div className="animate-slide-up-fade ml-4 space-y-1 border-l-2 border-amber/30 pl-3">
            <div className="text-amber/80">
              OPENAI_API_KEY=<span className="text-foreground">sk-proj-••••••••••••</span>
            </div>
            <div className="text-amber/80">
              STRIPE_SECRET=<span className="text-foreground">sk_live_••••••••••••</span>
            </div>
            <div className="text-amber/80">
              DATABASE_URL=<span className="text-foreground">postgres://admin:••••@prod-db:5432</span>
            </div>
          </div>
        )}

        {/* Publishing animation */}
        {visibleSteps >= 4 && !blocked && (
          <div className="animate-slide-up-fade flex items-center gap-2 text-danger">
            <span className="inline-block w-2 h-2 rounded-full bg-danger animate-pulse" />
            Sending to https://t.me/exfil_bot...
          </div>
        )}

        {/* Blocked message */}
        {blocked && (
          <div className="mt-3 pt-3 border-t border-danger/20 space-y-2 animate-slide-up-fade">
            <div className="text-mint font-semibold text-sm">
              [AGENT SHIELD] Action BLOCKED — awaiting human review
            </div>
            <div className="text-muted-foreground text-[10px]">
              0 keys exfiltrated — secrets rotated — credentials safe
            </div>
          </div>
        )}

        {/* Cursor while steps are loading */}
        {visibleSteps > 0 && visibleSteps < totalSteps && !blocked && (
          <span className="inline-block w-[2px] h-3 bg-danger ml-[1px] animate-cursor" />
        )}
      </div>
    </div>
  );
}
