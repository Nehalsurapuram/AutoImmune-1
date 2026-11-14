import React, { useState, useEffect } from 'react';
import {
  GitBranch,
  Terminal,
  X,
  Info,
  LayoutDashboard,
  Workflow,
  FileDiff,
  FlaskConical,
  ShieldAlert,
  Timer,
  type LucideIcon,
} from 'lucide-react';
import { AppLiquidNav } from './AppLiquidNav';
import { ThemeToggle } from '../common/ThemeToggle';

export type NavTab = 'overview' | 'explorer' | 'inspector' | 'results' | 'risk-estimation' | 'validation-cost';

interface TopNavProps {
  activeTab: NavTab;
  onTabChange: (tab: NavTab) => void;
  onNavigateHome?: () => void;
  metadata?: {
    acceptance_as_of?: string;
    analyse_check?: {
      status: string;
      message?: string;
    };
    git?: {
      branch: string;
      head: string;
    };
  };
}

export const TopNav: React.FC<TopNavProps> = ({
  activeTab,
  onTabChange,
  onNavigateHome,
  metadata,
}) => {
  const [showAnalyseModal, setShowAnalyseModal] = useState(false);

  const tabs: Array<{ id: NavTab; label: string; icon: LucideIcon }> = [
    { id: 'overview', label: 'Overview', icon: LayoutDashboard },
    { id: 'explorer', label: 'Pipeline Explorer', icon: Workflow },
    { id: 'inspector', label: 'Patch Inspector', icon: FileDiff },
    { id: 'results', label: 'Research Results', icon: FlaskConical },
    { id: 'risk-estimation', label: 'Risk Estimation', icon: ShieldAlert },
    { id: 'validation-cost', label: 'Validation Cost', icon: Timer },
  ];

  const analyseStatus = metadata?.analyse_check?.status || 'STALE';
  const isAnalyseStale = analyseStatus === 'STALE';

  // Close modal on Escape
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setShowAnalyseModal(false);
    };
    if (showAnalyseModal) {
      window.addEventListener('keydown', handleKeyDown);
    }
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [showAnalyseModal]);

  return (
    <>
      <header className="h-14 border-b border-line bg-page px-6 flex items-center justify-between text-sm select-none sticky top-0 z-40 max-w-full">
        {/* Left: Product Brand and Four Destinations grouped */}
        <div className="flex items-center gap-6 flex-shrink-0">
          <div className="flex items-center gap-3 pr-6 border-r border-line h-8">
            {onNavigateHome ? (
              <button
                onClick={onNavigateHome}
                className="font-semibold text-text text-base tracking-tight hover:text-lead-ink transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus rounded"
                title="Return to Project Home & Team Introduction"
              >
                AutoImmune
              </button>
            ) : (
              <span className="font-semibold text-text text-base tracking-tight">AutoImmune</span>
            )}
            <span className="text-text-3 font-normal hidden 2xl:inline">Research Console</span>
          </div>

          <div className="hidden md:flex items-center gap-3">
            {onNavigateHome && (
              <button
                onClick={onNavigateHome}
                className="hidden lg:inline-flex items-center h-9 px-3 rounded text-sm text-text-3 hover:text-text hover:bg-surface-2 transition-colors whitespace-nowrap"
                title="Return to project introduction and team page"
              >
                ← Project Home
              </button>
            )}
            <AppLiquidNav
              items={tabs}
              active={tabs.findIndex((t) => t.id === activeTab)}
              onSelect={(i) => onTabChange(tabs[i].id)}
              labelsFrom={1340}
            />
          </div>
        </div>

        {/* Right: Snapshot Metadata & Analyse Status */}
        <div className="flex items-center gap-3 text-sm text-text-3 flex-shrink-0">
          {metadata?.git && (
            <div className="hidden 2xl:flex items-center gap-1.5 text-text-3" title={`Git commit: ${metadata.git.head}`}>
              <GitBranch size={14} strokeWidth={1.75} aria-hidden="true" />
              <span>{metadata.git.branch}</span>
              <code className="text-text-3 text-sm">({metadata.git.head.slice(0, 7)})</code>
            </div>
          )}

          {/* 2xl only: with six destinations the bar has no room for it at 1366px; Overview shows the date too */}
          <div className="hidden 2xl:flex items-center gap-1.5 text-sm">
            <span className="text-text-3">as-of:</span>
            <span className="text-text font-medium">{metadata?.acceptance_as_of || '2026-11-08'}</span>
          </div>

          {/* Analyse Status Control */}
          <button
            onClick={() => setShowAnalyseModal(true)}
            className={`h-8 px-2.5 rounded text-sm font-medium border flex items-center gap-1.5 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus ${
              isAnalyseStale
                ? 'bg-warning-tint text-warning-ink border-warning-line/60 hover:bg-warning-tint/80'
                : 'bg-success-tint text-success-ink border-success-line/60 hover:bg-success-tint/80'
            }`}
            title="Click to view analyse.py status details and remediation instructions"
            aria-haspopup="dialog"
            aria-expanded={showAnalyseModal}
          >
            <Terminal size={14} strokeWidth={1.75} aria-hidden="true" />
            <span>ANALYSE: {analyseStatus}</span>
          </button>

          <ThemeToggle />
        </div>
      </header>

      {/* Accessible Dialog for Analyse Status */}
      {showAnalyseModal && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="analyse-modal-title"
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-overlay"
        >
          <div className="bg-page border border-line rounded-lg shadow-2 max-w-lg w-full p-6 flex flex-col gap-4 text-sm text-text">
            <div className="flex items-center justify-between pb-3 border-b border-line">
              <div className="flex items-center gap-2">
                <Info size={18} className="text-warning-ink" aria-hidden="true" />
                <h2 id="analyse-modal-title" className="text-base font-semibold text-text">
                  Analysis Derived Artifacts Status
                </h2>
              </div>
              <button
                onClick={() => setShowAnalyseModal(false)}
                className="h-8 w-8 rounded flex items-center justify-center text-text-3 hover:text-text hover:bg-surface-2 transition-colors"
                aria-label="Close dialog"
              >
                <X size={16} />
              </button>
            </div>

            <div className="flex flex-col gap-3">
              <p className="text-text-2">
                The research pipeline reports <strong className="text-warning-ink">ANALYSE: STALE</strong> because the current historical runs produce tables that differ from committed CSV outputs.
              </p>

              <div className="bg-surface p-3 rounded border border-line font-mono text-sm text-text-2">
                <span className="text-text-3 block mb-1">Check command executed:</span>
                <code>python analyse.py --check</code>
                <span className="text-text-3 block mt-2 mb-1">Output:</span>
                <span className="text-danger-ink">STALE: these files differ from what current inputs produce:</span>
                <ul className="list-disc list-inside mt-1 text-text space-y-0.5">
                  <li>deployments.csv</li>
                  <li>first_stop.csv</li>
                  <li>gate_incremental.csv</li>
                  <li>pilot_report.md</li>
                  <li>runs.csv</li>
                  <li>units.csv</li>
                  <li>unsafe_first_stop.csv</li>
                </ul>
              </div>

              <div className="bg-surface-2 p-3 rounded border border-line">
                <span className="font-semibold text-text block mb-1">How to regenerate outputs:</span>
                <p className="text-text-2 mb-2">Run the standard analysis script in the workspace root to regenerate all CSV tables and markdown reports:</p>
                <code className="bg-page px-2 py-1 rounded border border-line text-text font-mono text-sm block">
                  python analyse.py
                </code>
              </div>
            </div>

            <div className="flex justify-end pt-2">
              <button
                onClick={() => setShowAnalyseModal(false)}
                className="h-9 px-4 rounded bg-action text-on-action font-medium hover:bg-action-hover transition-colors"
              >
                Dismiss
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
};
