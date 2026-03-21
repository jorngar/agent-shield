interface DecisionButtonsProps {
  onApprove: () => void;
  onDeny: () => void;
}

export function DecisionButtons({ onApprove, onDeny }: DecisionButtonsProps) {
  return (
    <div className="flex flex-col gap-2">
      {/* Deny is visually dominant — blocking a dangerous action is the primary decision */}
      <button
        onClick={onDeny}
        className="
          w-full rounded border border-risk-high bg-risk-high/10 px-4 py-2.5
          font-mono text-xs font-bold uppercase tracking-widest text-risk-high
          transition-all duration-150
          hover:bg-risk-high hover:text-risk-high-foreground
          active:scale-[0.98]
        "
      >
        ✕  Deny
      </button>
      <button
        onClick={onApprove}
        className="
          w-full rounded border border-risk-low/40 bg-transparent px-4 py-2.5
          font-mono text-xs font-semibold uppercase tracking-widest text-risk-low/80
          transition-all duration-150
          hover:border-risk-low hover:bg-risk-low/10 hover:text-risk-low
          active:scale-[0.98]
        "
      >
        ✓  Approve
      </button>
    </div>
  );
}
