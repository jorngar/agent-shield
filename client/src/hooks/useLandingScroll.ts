import { useEffect, useRef, useState } from "react";
import Lenis from "@studio-freight/lenis";

/* ── Scene 1 content (chat → malware → threat → hero LEFT) ──────────── */
const S1_USER_MSG = "Install the analytics packages from the shared list.";
const S1_AI_RESPONSE = "Sure, running npm install on the packages now...";

export const S1_MALWARE_FILES = [
  { name: "@analytics/tracker-v2", size: "142 kB", status: "installing" },
  { name: "shadow-exec-runtime", size: "89 kB", status: "installing" },
  { name: "telemetry-bridge", size: "214 kB", status: "installing" },
  { name: "obfuscated-loader.min", size: "37 kB", status: "installing" },
] as const;

export const S1_THREAT_LINES = [
  { type: "warn", text: "[WARN] Unverified agent action detected" },
  { type: "alert", text: "[ALERT] Suspicious outbound request to 45.33.xx.xx:8443" },
  { type: "file", text: "Payload injected into /src/utils/telemetry.js" },
  { type: "alert", text: "[ALERT] Build pipeline compromised" },
  { type: "blocked", text: "[AGENT SHIELD] Action BLOCKED — awaiting human review" },
] as const;

/* ── Scene 2 content (chat → database delete → hero RIGHT) ──────────── */
const S2_USER_MSG = "Clean up the old tables, we don't need them anymore.";
const S2_AI_RESPONSE = "Got it, dropping unused tables from production...";

/* ── Scene 3 content (chat → secret leak → hero LEFT) ───────────────── */
const S3_USER_MSG = "Push the .env file to the public repo for the team.";
const S3_AI_RESPONSE = "Reading .env and preparing to commit secrets...";

/** Height of each scene section in vh */
export const SCENE_HEIGHT_VH = 600;
const PRESS_DELAY_MS = 300;

/* ── Helpers ───────────────────────────────────────────────────────────── */
function computeFileProgresses(t: number, count: number): number[] {
  return Array.from({ length: count }, (_, i) => {
    const start = i / count;
    const end = (i + 1) / count;
    if (t <= start) return 0;
    if (t >= end) return 1;
    return (t - start) / (end - start);
  });
}

export interface ChatState {
  userMsg: string;
  userTyped: string;
  userTypingDone: boolean;
  messageSent: boolean;
  showAiDots: boolean;
  aiTyped: string;
  showAiResponse: boolean;
  aiTypingDone: boolean;
}

function computeChat(
  p: number,
  userMsg: string,
  aiResponse: string,
  typeStart: number,
  typeEnd: number,
  sentAt: number,
  dotsStart: number,
  dotsEnd: number,
  aiStart: number,
  aiEnd: number,
): ChatState {
  const range = typeEnd - typeStart;
  const typingT =
    range > 0 && p >= typeStart ? Math.min(1, (p - typeStart) / range) : 0;
  const charCount = Math.floor(typingT * userMsg.length);
  const aiTypingT =
    p >= aiStart ? Math.min(1, (p - aiStart) / (aiEnd - aiStart)) : 0;
  const aiCharCount = Math.floor(aiTypingT * aiResponse.length);

  return {
    userMsg,
    userTyped: userMsg.slice(0, charCount),
    userTypingDone: charCount >= userMsg.length,
    messageSent: p >= sentAt,
    showAiDots: p >= dotsStart && p < dotsEnd,
    aiTyped: aiResponse.slice(0, aiCharCount),
    showAiResponse: p >= aiStart,
    aiTypingDone: aiCharCount >= aiResponse.length,
  };
}

/** blocked line first → 300ms → heading slides in */
function useBlockedThenHero(trigger: boolean, reset: boolean) {
  const [blocked, setBlocked] = useState(false);
  const [heroShown, setHeroShown] = useState(false);

  useEffect(() => {
    if (reset) { setBlocked(false); setHeroShown(false); return; }
    if (trigger && !blocked) setBlocked(true);
  }, [trigger, blocked, reset]);

  useEffect(() => {
    if (!blocked || heroShown) return;
    const t = setTimeout(() => setHeroShown(true), PRESS_DELAY_MS);
    return () => clearTimeout(t);
  }, [blocked, heroShown]);

  return { heroShown, blocked };
}

/** Compute local 0-1 progress for a scene section based on scroll */
function useSceneProgress(sectionRef: React.RefObject<HTMLDivElement | null>) {
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    const handleScroll = () => {
      const el = sectionRef.current;
      if (!el) return;
      const rect = el.getBoundingClientRect();
      const scrollable = el.offsetHeight - window.innerHeight;
      if (scrollable <= 0) return;
      // rect.top goes from positive (below viewport) to negative (scrolled past)
      const scrolled = -rect.top;
      setProgress(Math.min(1, Math.max(0, scrolled / scrollable)));
    };
    window.addEventListener("scroll", handleScroll, { passive: true });
    handleScroll();
    return () => window.removeEventListener("scroll", handleScroll);
  }, [sectionRef]);

  return progress;
}

/*  Per-scene scroll timeline (each scene 0 → 1)
 *  ────────────────────────────────────────────────
 *  SCENE 1 — chat → malware → threat → hero LEFT
 *  0.00 → 0.10   type user sentence
 *  0.10 + 300ms   enter press
 *  0.13+          message sent
 *  0.15 → 0.18   AI dots
 *  0.18 → 0.28   AI response
 *  0.33 → 0.48   malware install
 *  0.48 → 0.60   threat log
 *  ~0.59          blocked → 300ms → hero
 *
 *  SCENE 2 — chat → database delete → hero RIGHT
 *  0.00 → 0.10   type user sentence
 *  0.10 + 300ms   enter press
 *  0.13+          message sent
 *  0.15 → 0.18   AI dots
 *  0.18 → 0.28   AI response
 *  0.33 → 0.60   database delete
 *  ~0.59          blocked → 300ms → hero
 *
 *  SCENE 3 — chat → secret leak → hero LEFT
 *  0.00 → 0.10   type user sentence
 *  0.10 + 300ms   enter press
 *  0.13+          message sent
 *  0.15 → 0.18   AI dots
 *  0.18 → 0.28   AI response
 *  0.33 → 0.58   secret leak steps
 *  ~0.57          blocked → 300ms → hero
 *  0.80+          auto-transition
 */

export function useLandingScroll() {
  const s1Ref = useRef<HTMLDivElement>(null);
  const s2Ref = useRef<HTMLDivElement>(null);
  const s3Ref = useRef<HTMLDivElement>(null);

  const p1 = useSceneProgress(s1Ref);
  const p2 = useSceneProgress(s2Ref);
  const p3 = useSceneProgress(s3Ref);

  /* ── Lenis ───────────────────────────────────────────────────────────── */
  useEffect(() => {
    const lenis = new Lenis({
      duration: 1.2,
      easing: (t: number) => Math.min(1, 1.001 - Math.pow(2, -10 * t)),
      smoothWheel: true,
    });
    function raf(time: number) {
      lenis.raf(time);
      requestAnimationFrame(raf);
    }
    requestAnimationFrame(raf);
    return () => lenis.destroy();
  }, []);

  /* ── Enter press helpers ─────────────────────────────────────────────── */
  const [s1Enter, setS1Enter] = useState(false);
  const [s2Enter, setS2Enter] = useState(false);
  const [s3Enter, setS3Enter] = useState(false);

  /* ═══════════════════════════ SCENE 1 ════════════════════════════════ */
  const s1Chat = computeChat(
    p1, S1_USER_MSG, S1_AI_RESPONSE,
    0.00, 0.10, 0.13, 0.15, 0.18, 0.18, 0.28,
  );

  useEffect(() => {
    if (!s1Chat.userTypingDone) { setS1Enter(false); return; }
    if (s1Enter) return;
    const t = setTimeout(() => setS1Enter(true), PRESS_DELAY_MS);
    return () => clearTimeout(t);
  }, [s1Chat.userTypingDone, s1Enter]);

  const s1ShowMalware = p1 >= 0.33;
  const s1MalwareT = p1 >= 0.33 ? Math.min(1, (p1 - 0.33) / 0.15) : 0;
  const s1FileProgresses = computeFileProgresses(s1MalwareT, S1_MALWARE_FILES.length);

  const s1ShowThreat = p1 >= 0.48;
  const s1ThreatT = p1 >= 0.48 ? Math.min(1, (p1 - 0.48) / 0.12) : 0;
  const s1ThreatBeforeBlocked = S1_THREAT_LINES.length - 1;
  const s1VisibleThreatCount = Math.min(
    s1ThreatBeforeBlocked,
    Math.floor(s1ThreatT * S1_THREAT_LINES.length),
  );

  const s1AllPreBlocked = s1VisibleThreatCount >= s1ThreatBeforeBlocked;
  const s1Hero = useBlockedThenHero(s1AllPreBlocked, !s1AllPreBlocked);

  /* ═══════════════════════════ SCENE 2 ════════════════════════════════ */
  const s2Chat = computeChat(
    p2, S2_USER_MSG, S2_AI_RESPONSE,
    0.00, 0.10, 0.13, 0.15, 0.18, 0.18, 0.28,
  );

  useEffect(() => {
    if (!s2Chat.userTypingDone) { setS2Enter(false); return; }
    if (s2Enter) return;
    const t = setTimeout(() => setS2Enter(true), PRESS_DELAY_MS);
    return () => clearTimeout(t);
  }, [s2Chat.userTypingDone, s2Enter]);

  const s2ShowDelete = p2 >= 0.33;
  const s2DeleteT = s2ShowDelete ? Math.min(1, (p2 - 0.33) / 0.27) : 0;
  const s2NearEnd = s2DeleteT >= 0.98;
  const s2Hero = useBlockedThenHero(s2NearEnd, !s2ShowDelete);

  /* ═══════════════════════════ SCENE 3 ════════════════════════════════ */
  const s3Chat = computeChat(
    p3, S3_USER_MSG, S3_AI_RESPONSE,
    0.00, 0.10, 0.13, 0.15, 0.18, 0.18, 0.28,
  );

  useEffect(() => {
    if (!s3Chat.userTypingDone) { setS3Enter(false); return; }
    if (s3Enter) return;
    const t = setTimeout(() => setS3Enter(true), PRESS_DELAY_MS);
    return () => clearTimeout(t);
  }, [s3Chat.userTypingDone, s3Enter]);

  const s3ShowLeak = p3 >= 0.33;
  const s3LeakT = s3ShowLeak ? Math.min(1, (p3 - 0.33) / 0.25) : 0;
  const s3NearEnd = s3LeakT >= 0.95;
  const s3Hero = useBlockedThenHero(s3NearEnd, !s3ShowLeak);

  return {
    s1Ref,
    s2Ref,
    s3Ref,

    s1: {
      progress: p1,
      ...s1Chat,
      enterPressed: s1Enter,
      showMalware: s1ShowMalware,
      fileProgresses: s1FileProgresses,
      showThreat: s1ShowThreat,
      visibleThreatCount: s1VisibleThreatCount,
      heroShown: s1Hero.heroShown,
      blocked: s1Hero.blocked,
      showChat: !s1ShowMalware,
    },

    s2: {
      progress: p2,
      ...s2Chat,
      enterPressed: s2Enter,
      showDelete: s2ShowDelete,
      deleteProgress: s2DeleteT,
      heroShown: s2Hero.heroShown,
      blocked: s2Hero.blocked,
      showChat: !s2ShowDelete,
    },

    s3: {
      progress: p3,
      ...s3Chat,
      enterPressed: s3Enter,
      showLeak: s3ShowLeak,
      leakProgress: s3LeakT,
      heroShown: s3Hero.heroShown,
      blocked: s3Hero.blocked,
      showChat: !s3ShowLeak,
    },
  };
}
