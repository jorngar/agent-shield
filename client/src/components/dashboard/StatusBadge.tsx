import type { DecisionStatus } from "@/lib/types";

const config: Record<DecisionStatus, { label: string; className: string; dot: string }> = {
  pending: {
    label: "Pending",
    className: "bg-status-pending/20 text-status-pending border border-status-pending/40",
    dot: "bg-status-pending animate-pulse",
  },
  approved: {
    label: "Approved",
    className: "bg-status-approved/20 text-status-approved border border-status-approved/40",
    dot: "bg-status-approved",
  },
  denied: {
    label: "Denied",
    className: "bg-status-denied/20 text-status-denied border border-status-denied/40",
    dot: "bg-status-denied",
  },
};

interface StatusBadgeProps {
  status: DecisionStatus;
  className?: string;
}

export function StatusBadge({ status, className = "" }: StatusBadgeProps) {
  const { label, className: colorClass, dot } = config[status];
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${colorClass} ${className}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${dot}`} />
      {label}
    </span>
  );
}
