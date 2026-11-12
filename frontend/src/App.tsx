import React, { useState, useEffect, useCallback } from 'react';
import { TopNav, NavTab } from './components/layout/TopNav';
import { PipelineExplorer } from './pages/PipelineExplorer/PipelineExplorer';
import { Overview } from './pages/Overview/Overview';
import { PatchInspector } from './pages/PatchInspector/PatchInspector';
import { ResearchResults } from './pages/ResearchResults/ResearchResults';
import { LandingPage } from './pages/Landing/LandingPage';
import { EvidenceSnapshot } from './types/evidence';
import { AlertCircle, RotateCcw } from 'lucide-react';

export type AppRoute = 'landing' | 'console';

function getInitialRouteState(): { route: AppRoute; tab: NavTab } {
  if (typeof window === 'undefined') {
    return { route: 'landing', tab: 'overview' };
  }
  const path = window.location.pathname.toLowerCase();
  const hash = window.location.hash.toLowerCase();

  // If path or hash explicitly indicates console or console sub-views
  if (path.startsWith('/console') || hash.startsWith('#/console') || hash.startsWith('#console')) {
    let tab: NavTab = 'overview';
    if (path.includes('explorer') || path.includes('pipeline') || hash.includes('explorer') || hash.includes('pipeline')) {
      tab = 'explorer';
    } else if (path.includes('inspector') || path.includes('patches') || hash.includes('inspector') || hash.includes('patches')) {
      tab = 'inspector';
    } else if (path.includes('results') || path.includes('research') || hash.includes('results') || hash.includes('research')) {
      tab = 'results';
    }
    return { route: 'console', tab };
  }

  // Default entry route is always the research landing page
  return { route: 'landing', tab: 'overview' };
}

export const App: React.FC = () => {
  const [initial] = useState(getInitialRouteState);
  const [appRoute, setAppRoute] = useState<AppRoute>(initial.route);
  const [activeTab, setActiveTab] = useState<NavTab>(initial.tab);
  const [snapshot, setSnapshot] = useState<EvidenceSnapshot | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Synchronize route changes to browser history
  const navigateTo = useCallback((route: AppRoute, tab: NavTab = 'overview') => {
    setAppRoute(route);
    setActiveTab(tab);

    const targetPath = route === 'landing' ? '/' : (tab === 'overview' ? '/console' : `/console/${tab}`);
    if (window.location.pathname !== targetPath) {
      window.history.pushState({ route, tab }, '', targetPath);
    }
    // Scroll to top on route change
    window.scrollTo({ top: 0, behavior: 'instant' });
  }, []);

  // Listen for browser Back/Forward (popstate)
  useEffect(() => {
    const handlePopState = (e: PopStateEvent) => {
      if (e.state && e.state.route) {
        setAppRoute(e.state.route);
        setActiveTab(e.state.tab || 'overview');
      } else {
        const state = getInitialRouteState();
        setAppRoute(state.route);
        setActiveTab(state.tab);
      }
    };
    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, []);

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

  // 1. Landing Page Entry Route
  if (appRoute === 'landing') {
    return (
      <LandingPage
        snapshot={snapshot}
        onEnterConsole={(tab = 'overview') => navigateTo('console', tab)}
      />
    );
  }

  // 2. Existing Research Console with 4 Verified Screens
  return (
    <div className="min-h-[100dvh] flex flex-col bg-page text-text font-sans selection:bg-lead-tint selection:text-text overflow-x-hidden">
      <TopNav
        activeTab={activeTab}
        onTabChange={(tab) => navigateTo('console', tab)}
        onNavigateHome={() => navigateTo('landing')}
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
            onNavigate={(tab) => navigateTo('console', tab)}
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
            onNavigateToExplorer={() => navigateTo('console', 'explorer')}
            onNavigateToInspector={() => navigateTo('console', 'inspector')}
          />
        )}
      </main>
    </div>
  );
};
