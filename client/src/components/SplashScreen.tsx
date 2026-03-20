import { useEffect, useRef, useState } from "react";

interface SplashScreenProps {
  onDone: () => void;
}

// Linear interpolation — same easing Lenis uses internally
function lerp(a: number, b: number, t: number) {
  return a + (b - a) * t;
}

export function SplashScreen({ onDone }: SplashScreenProps) {
  const containerRef   = useRef<HTMLDivElement>(null);
  const yRef           = useRef(0);
  const exitingRef     = useRef(false);
  const rafRef         = useRef<number>(0);
  const [ready, setReady] = useState(false);

  // Lenis-style lerp slide-up exit
  const startExit = () => {
    if (exitingRef.current) return;
    exitingRef.current = true;

    const target = -(window.innerHeight + 20);

    const tick = () => {
      yRef.current = lerp(yRef.current, target, 0.072);
      if (containerRef.current) {
        containerRef.current.style.transform = `translateY(${yRef.current}px)`;
      }
      if (Math.abs(yRef.current - target) > 0.8) {
        rafRef.current = requestAnimationFrame(tick);
      } else {
        if (containerRef.current) containerRef.current.style.display = "none";
        onDone();
      }
    };

    rafRef.current = requestAnimationFrame(tick);
  };

  useEffect(() => {
    // Short pause for content animations to settle, then exit
    const tReady = setTimeout(() => setReady(true), 100);
    const tExit  = setTimeout(startExit, 1350);
    return () => {
      clearTimeout(tReady);
      clearTimeout(tExit);
      cancelAnimationFrame(rafRef.current);
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div
      ref={containerRef}
      className="fixed inset-0 z-50 flex flex-col items-center justify-center overflow-hidden select-none"
      style={{ backgroundColor: "oklch(0.115 0.042 238)", willChange: "transform" }}
    >
      {/* ── Dot grid background ─────────────────────────────────────────── */}
      <div
        className="animate-dot-grid pointer-events-none absolute inset-0"
        style={{
          backgroundImage:
            "radial-gradient(circle, oklch(0.592 0.095 214 / 0.55) 1px, transparent 1px)",
          backgroundSize: "28px 28px",
        }}
      />

      {/* ── Radial glow behind logo ─────────────────────────────────────── */}
      <div
        className="pointer-events-none absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2"
        style={{
          width: 380,
          height: 380,
          background:
            "radial-gradient(circle, oklch(0.592 0.095 214 / 0.14) 0%, transparent 70%)",
        }}
      />

      {/* ── Scan line ───────────────────────────────────────────────────── */}
      {ready && (
        <div className="pointer-events-none absolute inset-0 overflow-hidden">
          <div
            className="absolute inset-x-0 h-px"
            style={{
              background:
                "linear-gradient(to right, transparent, oklch(0.592 0.095 214 / 0.7) 40%, oklch(0.800 0.130 158 / 0.5) 60%, transparent)",
              animation: "splash-scan-line 1.1s 0.05s linear forwards",
            }}
          />
        </div>
      )}

      {/* ── Logo + wordmark ─────────────────────────────────────────────── */}
      <div className="relative flex flex-col items-center gap-7">

        {/* Logo mark */}
        <div className="animate-splash-logo relative flex h-24 w-24 items-center justify-center rounded-2xl">
          {/* Pulsing outer glow */}
          <div
            className="absolute inset-0 rounded-2xl"
            style={{
              boxShadow: "0 0 40px 8px oklch(0.592 0.095 214 / 0.25)",
              animation: "risk-glow-amb 3s ease-in-out infinite",
            }}
          />
          {/* Border */}
          <div className="absolute inset-0 rounded-2xl border border-primary/40 bg-primary/8" />

          {/* Logo image or fallback */}
          <img
            src="/logo.png"
            alt="AgentGuard"
            className="relative z-10 h-14 w-auto object-contain"
            onError={(e) => {
              e.currentTarget.style.display = "none";
              (e.currentTarget.nextElementSibling as HTMLElement | null)?.removeAttribute("hidden");
            }}
          />
          <svg
            className="relative z-10 hidden h-11 w-11 text-primary"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth={1.6}
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
          </svg>
        </div>

        {/* Text */}
        <div className="flex flex-col items-center gap-2">
          <span className="animate-splash-text font-mono text-2xl font-bold tracking-[0.22em] uppercase text-foreground">
            AgentGuard
          </span>
          <span className="animate-splash-sub font-mono text-[11px] uppercase tracking-[0.35em] text-primary">
            Every tool call verified
          </span>
        </div>

      </div>

      {/* ── Bottom tag ──────────────────────────────────────────────────── */}
      <div
        className="animate-splash-sub absolute bottom-8 flex items-center gap-2 font-mono text-[10px] text-muted-foreground/50"
        style={{ animationDelay: "0.9s" }}
      >
        <span className="h-1 w-1 rounded-full bg-risk-low animate-pulse" />
        <span>v0.1.0 · hackathon build</span>
      </div>
    </div>
  );
}
