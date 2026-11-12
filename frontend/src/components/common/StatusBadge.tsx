import React from 'react';
import {
  Check,
  X,
  AlertTriangle,
  Clock,
  Minus,
  SkipForward,
  ShieldAlert,
  AlertCircle,
  CheckCircle,
} from 'lucide-react';

interface StatusBadgeProps {
  status?: string | null;
  className?: string;
  showIcon?: boolean;
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({
  status = 'unknown',
  className = '',
  showIcon = true,
}) => {
  const norm = (status || '').toLowerCase().trim();
  const iconSize = 14;

  let label = status?.toUpperCase() || 'UNKNOWN';
  let badgeClasses = 'bg-surface-2 text-text-2 border border-line';
  let IconComponent = Minus;

  switch (norm) {
    case 'pass':
    case 'passed':
      label = 'PASS';
      badgeClasses = 'bg-success-tint text-success-ink border border-success-line/40';
      IconComponent = Check;
      break;

    case 'fail':
    case 'failed':
      label = 'FAIL';
      badgeClasses = 'bg-danger-tint text-danger-ink border border-danger-line/40 font-semibold';
      IconComponent = X;
      break;

    case 'error':
      label = 'ERROR';
      badgeClasses = 'bg-danger-tint text-danger-ink border border-danger-line/40 font-semibold';
      IconComponent = AlertTriangle;
      break;

    case 'timeout':
      label = 'TIMEOUT';
      badgeClasses = 'bg-warning-tint text-warning-ink border border-warning-line/40 font-semibold';
      IconComponent = Clock;
      break;

    case 'not_run':
    case 'not run':
      label = 'NOT RUN';
      badgeClasses = 'bg-surface-2 text-text-3 border border-line';
      IconComponent = Minus;
      break;

    case 'skipped':
      label = 'SKIPPED';
      badgeClasses = 'bg-surface-2 text-text-3 border border-line';
      IconComponent = SkipForward;
      break;

    case 'auto_apply':
    case 'auto apply':
      label = 'AUTO_APPLY';
      badgeClasses = 'bg-success-tint text-success-ink border border-success-line/40 font-semibold';
      IconComponent = CheckCircle;
      break;

    case 'escalate':
      label = 'ESCALATE';
      badgeClasses = 'bg-warning-tint text-warning-ink border border-warning-line/40 font-semibold';
      IconComponent = AlertCircle;
      break;

    case 'reject':
      label = 'REJECT';
      badgeClasses = 'bg-danger-tint text-danger-ink border border-danger-line/40 font-semibold';
      IconComponent = ShieldAlert;
      break;

    case 'promoted':
      label = 'PROMOTED';
      badgeClasses = 'bg-success-tint text-success-ink border border-success-line/40 font-semibold';
      IconComponent = Check;
      break;

    case 'rolled back':
    case 'rolled_back':
      label = 'ROLLED BACK';
      badgeClasses = 'bg-danger-tint text-danger-ink border border-danger-line/40 font-semibold';
      IconComponent = AlertTriangle;
      break;

    default:
      label = (status || 'UNKNOWN').toUpperCase();
      badgeClasses = 'bg-surface-2 text-text-3 border border-line';
      IconComponent = Minus;
  }

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded px-2.5 py-1 text-sm font-medium tracking-tight whitespace-nowrap ${badgeClasses} ${className}`}
    >
      {showIcon && <IconComponent size={iconSize} strokeWidth={2} aria-hidden="true" />}
      <span>{label}</span>
    </span>
  );
};
