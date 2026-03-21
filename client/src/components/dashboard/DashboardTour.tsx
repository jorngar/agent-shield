import Joyride, { type CallBackProps, STATUS } from "react-joyride";

const steps = [
  {
    target: "#tour-header",
    title: "AgentShield",
    content: "Real-time monitoring dashboard for AI agent actions. Every tool call your agent makes is intercepted and evaluated before execution.",
    disableBeacon: true,
    placement: "bottom" as const,
  },
  {
    target: "#tour-stats",
    title: "Stats Bar",
    content: "Live counts of total intercepts, pending decisions, approved, and denied actions. Red pending count means your agent is waiting on you.",
    placement: "bottom" as const,
  },
  {
    target: "#tour-intercept-list",
    title: "Intercept Stream",
    content: "Every agent tool call appears here in real-time via WebSocket. Colour-coded by risk — red is high, amber is medium, green is low.",
    placement: "right" as const,
  },
  {
    target: "#tour-inspector",
    title: "Inspector Panel",
    content: "Select an intercept to inspect it. Shows the full tool arguments, matched rules, risk score, and why it was flagged.",
    placement: "right" as const,
  },
  {
    target: "#tour-decision",
    title: "Decision Panel",
    content: "Approve or deny the selected agent action here. You'll be asked for a reason — this is sent back to the agent and logged.",
    placement: "left" as const,
  },
];

interface DashboardTourProps {
  run: boolean;
  onFinish: () => void;
}

export function DashboardTour({ run, onFinish }: DashboardTourProps) {
  function handleCallback(data: CallBackProps) {
    if ([STATUS.FINISHED, STATUS.SKIPPED].includes(data.status as typeof STATUS[keyof typeof STATUS])) {
      onFinish();
    }
  }

  return (
    <Joyride
      steps={steps}
      run={run}
      continuous
      showSkipButton
      showProgress
      callback={handleCallback}
      styles={{
        options: {
          primaryColor:       "#6ee7b7",
          backgroundColor:    "#0f172a",
          textColor:          "#e2e8f0",
          overlayColor:       "rgba(0,0,0,0.55)",
          arrowColor:         "#0f172a",
          zIndex:             9999,
        },
        tooltip: {
          borderRadius: "8px",
          border:       "1px solid rgba(255,255,255,0.08)",
          fontFamily:   "monospace",
          fontSize:     "12px",
        },
        tooltipTitle: {
          fontSize:   "13px",
          fontWeight: "700",
          color:      "#6ee7b7",
        },
        buttonNext: {
          backgroundColor: "#6ee7b7",
          color:           "#0f172a",
          fontFamily:      "monospace",
          fontSize:        "11px",
          fontWeight:      "700",
          borderRadius:    "4px",
          padding:         "6px 14px",
        },
        buttonBack: {
          color:      "#94a3b8",
          fontFamily: "monospace",
          fontSize:   "11px",
        },
        buttonSkip: {
          color:      "#64748b",
          fontFamily: "monospace",
          fontSize:   "11px",
        },
      }}
      locale={{
        back:  "← back",
        next:  "next →",
        skip:  "skip",
        last:  "done",
      }}
    />
  );
}
