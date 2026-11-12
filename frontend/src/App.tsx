import React, { useState, useEffect } from 'react';
import { TopNav, NavTab } from './components/layout/TopNav';
import { PipelineExplorer } from './pages/PipelineExplorer/PipelineExplorer';
import { Overview } from './pages/Overview/Overview';
import { PatchInspector } from './pages/PatchInspector/PatchInspector';
import { ResearchResults } from './pages/ResearchResults/ResearchResults';
import { EvidenceSnapshot } from './types/evidence';
import { AlertCircle, RotateCcw } from 'lucide-react';

export const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<NavTab>('overview');
  const [snapshot, setSnapshot] = useState<EvidenceSnapshot | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const resp = await fetch('/data/evidence_snapshot.json');
      if (!resp.ok) {
        throw new Error(`HTTP ${resp.status}: Failed to load evidence snapshot`);
      }
      const data: EvidenceSnapshot = await resp.json();
      setSnapshot(data);
    } catch (err: any) {
      setError(err?.message || 'Failed to load research evidence');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  if (isLoading) {
    return (
      <div className="min-h-[100dvh] bg-page flex flex-col items-center justify-center p-6 text-sm text-text-2">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 border-2 border-line-strong border-t-text rounded-full animate-spin" />
          <span className="font-mono text-sm">Loading authoritative research evidence snapshot...</span>
        </div>
      </div>
    );
  }

  if (error || !snapshot) {
    return (
      <div className="min-h-[100dvh] bg-page flex flex-col items-center justify-center p-6 text-sm">
        <div className="max-w-md p-6 bg-surface border border-danger-line/40 rounded flex flex-col gap-4">
          <div className="flex items-center gap-2 text-danger-ink font-semibold text-base">
            <AlertCircle size={18} />
            <span>Evidence Loading Error</span>
          </div>
          <p className="text-text-2 leading-relaxed text-sm">
            {error || 'No research evidence data found at /data/evidence_snapshot.json.'}
          </p>
          <div className="text-sm text-text-3 font-mono bg-surface-2 p-2.5 rounded">
            Run: python tools/export_ui_data.py
          </div>
          <button
            onClick={loadData}
            className="self-start h-9 px-4 bg-action text-on-action rounded text-sm font-medium hover:bg-action-hover transition-colors flex items-center gap-2"
          >
            <RotateCcw size={14} />
            <span>Retry</span>
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-[100dvh] flex flex-col bg-page text-text font-sans selection:bg-lead-tint selection:text-text overflow-x-hidden">
      <TopNav
        activeTab={activeTab}
        onTabChange={setActiveTab}
        metadata={{
          acceptance_as_of: snapshot.metadata?.acceptance_as_of,
          analyse_check: snapshot.metadata?.analyse_check,
          git: snapshot.metadata?.git,
        }}
      />

      <main className="flex-1 flex flex-col overflow-hidden">
        {activeTab === 'overview' && (
          <Overview
            snapshot={snapshot}
            onNavigate={(tab) => setActiveTab(tab)}
          />
        )}

        {activeTab === 'explorer' && (
          <PipelineExplorer
            runs={snapshot.runs}
            initialRunId="f06-live-live-20261108t193456z"
          />
        )}

        {activeTab === 'inspector' && (
          <PatchInspector
            candidates={snapshot.candidates}
          />
        )}

        {activeTab === 'results' && (
          <ResearchResults
            snapshot={snapshot}
            onNavigateToExplorer={() => setActiveTab('explorer')}
            onNavigateToInspector={() => setActiveTab('inspector')}
          />
        )}
      </main>
    </div>
  );
};
