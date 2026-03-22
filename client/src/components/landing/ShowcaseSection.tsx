import { useEffect, useRef } from "react";
import { Link } from "react-router-dom";
import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { Shield, Radar, Brain, ShieldCheck, ArrowRight } from "lucide-react";

gsap.registerPlugin(ScrollTrigger);

const FEATURES = [
  {
    title: "Real-Time Monitoring",
    desc: "Every AI tool call is intercepted and analyzed before execution — prevent your agent from hallucination, database wipes, and secret leaks are caught instantly.",
  },
  {
    title: "Human-in-the-Loop",
    desc: "High-risk actions are paused and surfaced for human review. You stay in control while your agents stay productive.",
  },
  {
    title: "Threat Intelligence",
    desc: "Built-in threat scoring powered by pattern analysis and behavioral heuristics — risk is quantified before damage is done.",
  },
  {
    title: "Zero Trust by Default",
    desc: "No tool call is trusted implicitly. Every action is verified against configurable policies before it reaches your infrastructure.",
  },
];

const HORIZONTAL_ITEMS = [
  { icon: Shield, label: "Intercept", desc: "Capture every tool call" },
  { icon: Radar, label: "Analyze", desc: "Score risk in milliseconds" },
  { icon: Brain, label: "Decide", desc: "Auto-approve or escalate" },
  { icon: ShieldCheck, label: "Protect", desc: "Block dangerous actions" },
];

export function ShowcaseSection() {
  const sectionRef = useRef<HTMLDivElement>(null);
  const verticalRef = useRef<HTMLDivElement>(null);
  const colLeftRef = useRef<HTMLDivElement>(null);
  const horizontalRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const ctx = gsap.context(() => {
      /* ── Vertical: pin left heading, parallax scroll ──────────────── */
      const tl = gsap.timeline({ paused: true });
      tl.fromTo(
        colLeftRef.current,
        { y: 0 },
        { y: "170vh", duration: 1, ease: "none" },
        0,
      );

      ScrollTrigger.create({
        animation: tl,
        trigger: verticalRef.current,
        start: "top top",
        end: "bottom center",
        scrub: true,
      });

      /* ── Horizontal: scroll-driven carousel ───────────────────────── */
      const boxes = gsap.utils.toArray<HTMLElement>(".showcase-h-item");
      if (boxes.length && horizontalRef.current) {
        gsap.to(boxes, {
          xPercent: -100 * (boxes.length - 1),
          ease: "sine.out",
          scrollTrigger: {
            trigger: horizontalRef.current,
            pin: true,
            scrub: 3,
            snap: 1 / (boxes.length - 1),
            end: "+=" + horizontalRef.current.offsetWidth,
          },
        });
      }
    }, sectionRef);

    return () => ctx.revert();
  }, []);

  return (
    <div ref={sectionRef} className="showcase-root">
      {/* ═══════════ VERTICAL SECTION ═══════════ */}
      <section ref={verticalRef} className="showcase-vertical">
        <div className="showcase-container">
          <div className="showcase-v-content">
            {/* Left — sticky heading */}
            <div ref={colLeftRef} className="showcase-v-left">
              <h2 className="showcase-heading">
                <span>About</span>
                <span>Agent</span>
                <span>Shield</span>
              </h2>
            </div>

            {/* Right — feature items */}
            <div className="showcase-v-right">
              {FEATURES.map((f, i) => (
                <div key={i} className="showcase-v-item">
                  <h3 className="showcase-subheading">{f.title}</h3>
                  <p className="showcase-body">{f.desc}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* ═══════════ HORIZONTAL SECTION ═══════════ */}
      <section ref={horizontalRef} className="showcase-horizontal">
        <div className="showcase-container">
          <div className="showcase-h-content">
            {HORIZONTAL_ITEMS.map((item, i) => (
              <div key={i} className="showcase-h-item">
                <item.icon className="showcase-h-icon" strokeWidth={1.5} />
                <div className="showcase-h-label">{item.label}</div>
                <div className="showcase-h-desc">{item.desc}</div>
              </div>
            ))}

            {/* 5th item — Dashboard CTA with blurred bg image */}
            <Link to="/dashboard" className="showcase-h-item showcase-h-cta">
              <div className="showcase-h-cta-bg" />
              <div className="showcase-h-cta-content">
                <ArrowRight className="showcase-h-icon" strokeWidth={1.5} />
                <div className="showcase-h-label">Dashboard</div>
                <div className="showcase-h-desc">Enter the control center</div>
              </div>
            </Link>
          </div>
        </div>
      </section>
    </div>
  );
}
