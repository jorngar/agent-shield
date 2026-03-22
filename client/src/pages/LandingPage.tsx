import { useLandingScroll, SCENE_HEIGHT_VH } from "@/hooks/useLandingScroll";
import { S1_MALWARE_FILES, S1_THREAT_LINES } from "@/hooks/useLandingScroll";
import { ChatBox } from "@/components/landing/ChatBox";
import { MalwareInstall } from "@/components/landing/MalwareInstall";
import { ThreatLog } from "@/components/landing/ThreatLog";
import { DatabaseDelete } from "@/components/landing/DatabaseDelete";
import { SecretLeak } from "@/components/landing/SecretLeak";
import { ShowcaseSection } from "@/components/landing/ShowcaseSection";

const sectionHeight = `${SCENE_HEIGHT_VH}vh`;

const DotGrid = () => (
  <div
    className="pointer-events-none absolute inset-0 animate-dot-grid"
    style={{
      backgroundImage:
        "radial-gradient(oklch(0.592 0.095 214 / 0.25) 1px, transparent 1px)",
      backgroundSize: "24px 24px",
    }}
  />
);

export default function LandingPage() {
  const { s1Ref, s2Ref, s3Ref, s1, s2, s3 } = useLandingScroll();

  return (
    <div>
      {/* ════════════════════ SCENE 1 ════════════════════ */}
      <div ref={s1Ref} style={{ height: sectionHeight }} className="relative">
        <div className="sticky top-0 h-screen flex items-center justify-center bg-background overflow-hidden">
          <DotGrid />

          {/* Hero heading — LEFT */}
          <div
            className={[
              "absolute left-6 md:left-12 lg:left-20 max-w-md transition-all duration-700 ease-out z-10",
              s1.heroShown
                ? "opacity-100 translate-x-0"
                : "opacity-0 -translate-x-10 pointer-events-none",
            ].join(" ")}
          >
            <h1 className="text-4xl md:text-5xl lg:text-6xl font-bold leading-tight tracking-tight text-foreground">
              We Checked 
              <br />
              Your Tool Calls,
              <br />
              <span className="text-teal">Protect Your</span>
              <br />
              <span className="text-teal">Info</span>
            </h1>
            <p className="mt-6 text-muted-foreground text-base md:text-lg">
              Agent Shield monitors every AI action in real time — catching
              threats before they reach your codebase.
            </p>
          </div>

          {/* Panels — slide RIGHT on hero */}
          <div
            className={[
              "relative w-full max-w-2xl px-6 flex flex-col gap-4 transition-all duration-700 ease-out",
              s1.heroShown
                ? "translate-x-[30%] scale-90 origin-right"
                : "translate-x-0 scale-100",
            ].join(" ")}
          >
            {s1.showChat && (
              <ChatBox
                userMsg={s1.userMsg}
                userTyped={s1.userTyped}
                userTypingDone={s1.userTypingDone}
                enterPressed={s1.enterPressed}
                messageSent={s1.messageSent}
                showAiDots={s1.showAiDots}
                aiTyped={s1.aiTyped}
                showAiResponse={s1.showAiResponse}
                aiTypingDone={s1.aiTypingDone}
              />
            )}

            {s1.showMalware && (
              <MalwareInstall
                files={S1_MALWARE_FILES}
                fileProgresses={s1.fileProgresses}
              />
            )}

            {s1.showThreat && (
              <ThreatLog
                lines={S1_THREAT_LINES.slice(0, -1)}
                visibleCount={s1.visibleThreatCount}
                blockedLine={S1_THREAT_LINES[S1_THREAT_LINES.length - 1]}
                showBlocked={s1.blocked}
              />
            )}

            {/* Scroll hint */}
            {s1.progress < 0.05 && (
              <div className="mt-4 flex flex-col items-center gap-2 text-muted-foreground/50 animate-slide-up-fade">
                <span className="text-xs font-mono tracking-wide">
                  scroll to begin
                </span>
                <div className="w-5 h-8 rounded-full border border-muted-foreground/30 flex items-start justify-center p-1">
                  <div className="w-1 h-2 rounded-full bg-muted-foreground/50 animate-bounce" />
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ════════════════════ SCENE 2 ════════════════════ */}
      <div ref={s2Ref} style={{ height: sectionHeight }} className="relative">
        <div className="sticky top-0 h-screen flex items-center justify-center bg-background overflow-hidden">
          <DotGrid />

          {/* Panels — slide LEFT on hero */}
          <div
            className={[
              "relative w-full max-w-2xl px-6 flex flex-col gap-4 transition-all duration-700 ease-out",
              s2.heroShown
                ? "-translate-x-[30%] scale-90 origin-left"
                : "translate-x-0 scale-100",
            ].join(" ")}
          >
            {s2.showChat && (
              <ChatBox
                userMsg={s2.userMsg}
                userTyped={s2.userTyped}
                userTypingDone={s2.userTypingDone}
                enterPressed={s2.enterPressed}
                messageSent={s2.messageSent}
                showAiDots={s2.showAiDots}
                aiTyped={s2.aiTyped}
                showAiResponse={s2.showAiResponse}
                aiTypingDone={s2.aiTypingDone}
              />
            )}

            {s2.showDelete && (
              <DatabaseDelete
                deleteProgress={s2.deleteProgress}
                blocked={s2.blocked}
              />
            )}
          </div>

          {/* Hero heading — RIGHT */}
          <div
            className={[
              "absolute right-6 md:right-12 lg:right-20 max-w-md transition-all duration-700 ease-out z-10",
              s2.heroShown
                ? "opacity-100 translate-x-0"
                : "opacity-0 translate-x-10 pointer-events-none",
            ].join(" ")}
          >
            <h1 className="text-4xl md:text-5xl lg:text-6xl font-bold leading-tight tracking-tight text-foreground text-right">
              Mistake?
              <br />
              No Worry
              <br />
              <span className="text-teal">AGENT SHIELD</span>
              <br />
              <span className="text-teal">GOT YOU</span>
            </h1>
            <p className="mt-6 text-muted-foreground text-base md:text-lg text-right">
              Even catastrophic mistakes are caught before they happen.
              Your data stays safe — always.
            </p>
          </div>
        </div>
      </div>

      {/* ════════════════════ SCENE 3 ════════════════════ */}
      <div ref={s3Ref} style={{ height: sectionHeight }} className="relative">
        <div className="sticky top-0 h-screen flex items-center justify-center bg-background overflow-hidden">
          <DotGrid />

          {/* Hero heading — LEFT */}
          <div
            className={[
              "absolute left-6 md:left-12 lg:left-20 max-w-md transition-all duration-700 ease-out z-10",
              s3.heroShown
                ? "opacity-100 translate-x-0"
                : "opacity-0 -translate-x-10 pointer-events-none",
            ].join(" ")}
          >
            <h1 className="text-4xl md:text-5xl lg:text-6xl font-bold leading-tight tracking-tight text-foreground">
              We Secure
              <br />
              Your
              <br />
              <span className="text-teal">Secret Keys</span>
            </h1>
            <p className="mt-6 text-muted-foreground text-base md:text-lg">
              API keys, credentials, and secrets are intercepted before
              they ever leave your environment.
            </p>
          </div>

          {/* Panels — slide RIGHT on hero */}
          <div
            className={[
              "relative w-full max-w-2xl px-6 flex flex-col gap-4 transition-all duration-700 ease-out",
              s3.heroShown
                ? "translate-x-[30%] scale-90 origin-right"
                : "translate-x-0 scale-100",
            ].join(" ")}
          >
            {s3.showChat && (
              <ChatBox
                userMsg={s3.userMsg}
                userTyped={s3.userTyped}
                userTypingDone={s3.userTypingDone}
                enterPressed={s3.enterPressed}
                messageSent={s3.messageSent}
                showAiDots={s3.showAiDots}
                aiTyped={s3.aiTyped}
                showAiResponse={s3.showAiResponse}
                aiTypingDone={s3.aiTypingDone}
              />
            )}

            {s3.showLeak && (
              <SecretLeak
                leakProgress={s3.leakProgress}
                blocked={s3.blocked}
              />
            )}
          </div>
        </div>
      </div>

      {/* ════════════════════ SHOWCASE (after scenes) ════════════════════ */}
      <ShowcaseSection />
    </div>
  );
}
