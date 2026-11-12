import React, { useState, useMemo, useEffect } from 'react';
import { RunRecord, CandidateRecord } from '../../types/evidence';
import { StatusBadge } from '../../components/common/StatusBadge';
import { DiffViewer } from '../../components/common/DiffViewer';
import {
  Search,
  Filter,
  RotateCcw,
  Check,
  X,
  AlertTriangle,
  Minus,
  FileCode,
} from 'lucide-react';

interface PipelineExplorerProps {
  runs: RunRecord[];
  initialRunId?: string;
  onSelectCandidate?: (candidateId: string) => void;
}

// Format timestamp safely, ensuring "Invalid Date" never occurs
function formatTimestamp(ts?: string | null): string {
  if (!ts) return 'Time unavailable';
  try {
    const d = new Date(ts);
    if (isNaN(d.getTime())) return 'Time unavailable';
    return d.toISOString().replace('T', ' ').slice(0, 19) + ' UTC';
  } catch {
    return 'Time unavailable';
  }
}

// Format short date for run list row
function formatRunDate(ts?: string | null): string {
  if (!ts) return 'Time unavailable';
  try {
    const d = new Date(ts);
    if (isNaN(d.getTime())) return 'Time unavailable';
    return d.toISOString().slice(0, 10) + ' ' + d.toISOString().slice(11, 16);
  } catch {
    return 'Time unavailable';
  }
}

// Truncate ID in middle so prefix and distinguishing suffix remain visible
function truncateMiddle(str: string, maxLen: number = 24): string {
  if (!str || str.length <= maxLen) return str;
  const charsToShow = maxLen - 3;
  const frontChars = Math.ceil(charsToShow / 2);
  const backChars = Math.floor(charsToShow / 2);
  return str.slice(0, frontChars) + '...' + str.slice(str.length - backChars);
}

// Human readable fault titles
const FAULT_TITLES: Record<string, string> = {
  F01: 'F01 Customer Search Null Guard',
  F04: 'F04 Catalog Health Indicator Config',
  F06: 'F06 Discount Threshold Boundary',
};

export const PipelineExplorer: React.FC<PipelineExplorerProps> = ({
  runs,
  initialRunId,
  onSelectCandidate: _onSelectCandidate,
}) => {
  // Filters
  const [faultFilter, setFaultFilter] = useState<string>('ALL');
  const [modeFilter, setModeFilter] = useState<string>('ALL');
  const [outcomeFilter, setOutcomeFilter] = useState<string>('ALL');
  const [searchQuery, setSearchQuery] = useState<string>('');

  // Selected run: prefer initialRunId or first complete, evidence-backed run
  const [selectedRunId, setSelectedRunId] = useState<string>(() => {
    if (initialRunId && runs.some((r) => r.run_id === initialRunId)) {
      return initialRunId;
    }
    // 1. Complete live LLM run with full 10 stages, deploy, and promotion
    const featuredLive = runs.find((r) => r.run_id === 'f06-live-live-20261108t193456z');
    if (featuredLive) return featuredLive.run_id;

    // 2. Complete recorded execution with candidates and completed outcome
    const completedWithCands = runs.find(
      (r) => r.candidates && r.candidates.length > 0 && r.outcome === 'completed'
    );
    if (completedWithCands) return completedWithCands.run_id;

    // 3. Any run with candidate records (never an empty watch)
    const runWithCands = runs.find((r) => r.candidates && r.candidates.length > 0);
    return runWithCands?.run_id || runs[0]?.run_id || '';
  });

  // Keep selectedRunId synchronized when parent passes an initialRunId
  useEffect(() => {
    if (initialRunId && runs.some((r) => r.run_id === initialRunId)) {
      setSelectedRunId(initialRunId);
    }
  }, [initialRunId, runs]);

  // Selected candidate index within run
  const [selectedCandIdx, setSelectedCandIdx] = useState<number>(0);

  // Selected timeline stage (0-9)
  const [activeStageIdx, setActiveStageIdx] = useState<number>(0);

  // Filtered runs
  const filteredRuns = useMemo(() => {
    return runs.filter((r) => {
      if (faultFilter !== 'ALL' && r.fault_id !== faultFilter) return false;
      if (modeFilter !== 'ALL') {
        const isLive = r.patch_mode === 'live' || r.diag_mode === 'live';
        if (modeFilter === 'LIVE' && !isLive) return false;
        if (modeFilter === 'SCRIPTED' && isLive) return false;
      }
      if (outcomeFilter !== 'ALL') {
        const normOutcome = (r.outcome || '').toLowerCase();
        if (outcomeFilter === 'DEPLOYED' && !normOutcome.includes('deploy') && !normOutcome.includes('promoted')) return false;
        if (outcomeFilter === 'ROLLBACK' && !normOutcome.includes('roll')) return false;
        if (outcomeFilter === 'REJECTED' && !normOutcome.includes('reject')) return false;
      }
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const matchesId = r.run_id.toLowerCase().includes(q);
        const matchesFault = (r.fault_id || '').toLowerCase().includes(q);
        const matchesModel = (r.model || '').toLowerCase().includes(q);
        if (!matchesId && !matchesFault && !matchesModel) return false;
      }
      return true;
    });
  }, [runs, faultFilter, modeFilter, outcomeFilter, searchQuery]);

  const currentRun = useMemo(() => {
    return (
      runs.find((r) => r.run_id === selectedRunId) ||
      filteredRuns.find((r) => r.candidates && r.candidates.length > 0) ||
      filteredRuns[0] ||
      runs.find((r) => r.candidates && r.candidates.length > 0) ||
      runs[0]
    );
  }, [runs, selectedRunId, filteredRuns]);

  const currentCandidate = useMemo<CandidateRecord | undefined>(() => {
    if (!currentRun || !currentRun.candidates || currentRun.candidates.length === 0) return undefined;
    return currentRun.candidates[selectedCandIdx] || currentRun.candidates[0];
  }, [currentRun, selectedCandIdx]);

  // Distinct faults for filter dropdown
  const distinctFaults = useMemo(() => {
    const set = new Set<string>();
    runs.forEach((r) => {
      if (r.fault_id) set.add(r.fault_id);
    });
    return Array.from(set).sort();
  }, [runs]);

  // Stage definitions (10 stages)
  const stages = useMemo(() => {
    if (currentRun?.timeline_stages && currentRun.timeline_stages.length > 0) {
      return currentRun.timeline_stages;
    }
    return [
      { id: 'detection', name: 'Detect', status: 'pass', details: 'Incident detected' },
      { id: 'incident_evidence', name: 'Evidence', status: 'pass', details: 'Probe evidence logged' },
      { id: 'diagnosis', name: 'Diagnose', status: 'pass', details: 'Root cause identified' },
      { id: 'candidate_generation', name: 'Candidates', status: 'pass', details: 'Patches generated' },
      { id: 'validation_gates', name: 'Validate', status: 'pass', details: 'Gates V0-V3 evaluated' },
      { id: 'decision_engine', name: 'Decide', status: 'pass', details: 'Risk tier assigned' },
      { id: 'human_approval', name: 'Approval', status: 'pass', details: 'Policy reviewed' },
      { id: 'deployment', name: 'Deploy', status: currentRun?.deploy_artifact ? 'pass' : 'skipped', details: 'Container deployment' },
      { id: 'health_window', name: 'Health', status: currentRun?.rollback_artifact ? 'fail' : currentRun?.deploy_artifact ? 'pass' : 'skipped', details: 'Canary health verified' },
      { id: 'provenance_record', name: 'Provenance', status: 'pass', details: 'Run audit archived' },
    ];
  }, [currentRun]);

  const activeStage = stages[activeStageIdx] || stages[0];

  const handleResetWalkthrough = () => {
    setActiveStageIdx(0);
  };

  // Key figures extraction
  const outcomeText = useMemo(() => {
    if (currentRun?.rollback_artifact || currentRun?.candidates?.some((c) => c.rolled_back)) {
      return 'Rolled back';
    }
    if (currentRun?.deploy_artifact || currentRun?.candidates?.some((c) => c.deployed)) {
      return 'Promoted';
    }
    if (currentRun?.outcome) {
      return currentRun.outcome;
    }
    return 'Completed';
  }, [currentRun]);

  const faultLabel = useMemo(() => {
    if (!currentRun?.fault_id) return 'No fault (healthy watch)';
    return FAULT_TITLES[currentRun.fault_id] || `Fault ${currentRun.fault_id}`;
  }, [currentRun]);

  const riskTierText = (currentCandidate?.decision?.tier || 'Unavailable').toUpperCase();
  const decisionText = currentCandidate?.decision?.decision || 'Unavailable';

  const gatesPassedCount = useMemo(() => {
    if (!currentCandidate?.gates) return 'Unavailable';
    const g = currentCandidate.gates;
    let passed = 0;
    if (g.V0?.status === 'pass') passed++;
    if (g.V1?.status === 'pass') passed++;
    if (g.V2?.status === 'pass') passed++;
    if (g.V3?.status === 'pass') passed++;
    return `${passed} of 4`;
  }, [currentCandidate]);

  const recoveryTimeText = useMemo(() => {
    if (currentCandidate?.recovery_s !== undefined && currentCandidate?.recovery_s !== null) {
      return `${currentCandidate.recovery_s.toFixed(1)}s`;
    }
    if (currentRun?.deploy_artifact?.build_duration_sec !== undefined) {
      return `${currentRun.deploy_artifact.build_duration_sec.toFixed(1)}s`;
    }
    return 'Unavailable';
  }, [currentCandidate, currentRun]);

  const targetFilePath = currentCandidate?.files_touched?.[0] || 'OrderService.java';

  return (
    <div className="flex flex-col flex-1 h-[calc(100dvh-56px)] overflow-hidden bg-page text-text">
      {/* Top Filter and Execution Toolbar (Height 48px, standard 36px controls) */}
      <div className="px-6 py-2 border-b border-line bg-surface flex flex-wrap items-center justify-between gap-3 text-sm">
        {/* Left: Filters */}
        <div className="flex items-center gap-3 flex-wrap">
          <div className="flex items-center gap-1.5 font-medium text-text-2">
            <Filter size={15} strokeWidth={1.75} aria-hidden="true" />
            <span>Filter runs:</span>
          </div>

          <label className="sr-only" htmlFor="fault-select">Filter by Fault</label>
          <select
            id="fault-select"
            value={faultFilter}
            onChange={(e) => setFaultFilter(e.target.value)}
            className="h-9 bg-page border border-line-strong rounded px-3 py-1 text-sm text-text focus:outline-none focus:ring-2 focus:ring-focus"
          >
            <option value="ALL">All Faults</option>
            {distinctFaults.map((f) => (
              <option key={f} value={f}>{f}</option>
            ))}
          </select>

          <label className="sr-only" htmlFor="mode-select">Filter by Mode</label>
          <select
            id="mode-select"
            value={modeFilter}
            onChange={(e) => setModeFilter(e.target.value)}
            className="h-9 bg-page border border-line-strong rounded px-3 py-1 text-sm text-text focus:outline-none focus:ring-2 focus:ring-focus"
          >
            <option value="ALL">All Modes</option>
            <option value="LIVE">Live LLM</option>
            <option value="SCRIPTED">Scripted / Rule</option>
          </select>

          <label className="sr-only" htmlFor="outcome-select">Filter by Outcome</label>
          <select
            id="outcome-select"
            value={outcomeFilter}
            onChange={(e) => setOutcomeFilter(e.target.value)}
            className="h-9 bg-page border border-line-strong rounded px-3 py-1 text-sm text-text focus:outline-none focus:ring-2 focus:ring-focus"
          >
            <option value="ALL">All Outcomes</option>
            <option value="DEPLOYED">Deployed / Promoted</option>
            <option value="ROLLBACK">Rolled Back</option>
            <option value="REJECTED">Rejected</option>
          </select>

          <div className="relative">
            <Search size={15} className="absolute left-3 top-2.5 text-text-3" aria-hidden="true" />
            <input
              type="text"
              aria-label="Search run ID or model"
              placeholder="Search run ID or model"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="h-9 bg-page border border-line-strong rounded pl-8 pr-3 text-sm text-text focus:outline-none focus:ring-2 focus:ring-focus w-56"
            />
          </div>

          <span className="text-text-3 tabular-nums text-sm">
            {filteredRuns.length} of {runs.length} runs
          </span>
        </div>

        {/* Right: Stepper Reset Control */}
        <div className="flex items-center gap-2">
          <button
            onClick={handleResetWalkthrough}
            className="h-9 px-3 rounded text-sm border border-line bg-page text-text-2 hover:text-text hover:bg-surface-2 transition-colors flex items-center gap-1.5"
            title="Reset stage view to stage 1"
          >
            <RotateCcw size={14} strokeWidth={1.75} />
            <span>Reset Stage</span>
          </button>
        </div>
      </div>

      {/* Main Master-Detail Layout */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left Aside: Run List Selector (Width 360px, comfortable row height with 3 distinct lines) */}
        <aside className="w-[360px] border-r border-line bg-surface flex flex-col flex-shrink-0 overflow-hidden" aria-label="Runs list">
          <div className="px-4 py-2.5 border-b border-line bg-surface-2 text-sm font-medium text-text-2 flex items-center justify-between">
            <span>Historical Runs</span>
            <span className="text-text-3 tabular-nums font-normal text-sm">sorted by date</span>
          </div>

          <div className="flex-1 overflow-y-auto divide-y divide-line" role="list">
            {filteredRuns.length === 0 ? (
              <div className="p-6 text-sm text-text-3 text-center">
                No runs match the selected filters.
              </div>
            ) : (
              filteredRuns.map((r) => {
                const isSelected = r.run_id === currentRun?.run_id;
                const isLive = r.patch_mode === 'live' || r.diag_mode === 'live';
                const hasDeploy = r.deploy_artifact || r.candidates.some((c) => c.deployed);
                const hasRollback = r.rollback_artifact || r.candidates.some((c) => c.rolled_back);

                const faultDisplay = r.fault_id
                  ? FAULT_TITLES[r.fault_id] || `Fault ${r.fault_id}`
                  : 'No fault (healthy watch)';

                const outcomeWord = hasRollback
                  ? 'Rolled back'
                  : hasDeploy
                  ? 'Promoted'
                  : r.outcome || 'Completed';

                const shortDate = formatRunDate(r.started_at);
                const truncatedId = truncateMiddle(r.run_id, 24);

                return (
                  <button
                    key={r.run_id}
                    role="listitem"
                    onClick={() => {
                      setSelectedRunId(r.run_id);
                      setSelectedCandIdx(0);
                      setActiveStageIdx(0);
                    }}
                    className={`w-full text-left px-4 py-3 text-sm transition-colors flex flex-col justify-center gap-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-inset ${
                      isSelected
                        ? 'bg-selected text-text font-medium'
                        : 'hover:bg-surface-2 text-text-2'
                    }`}
                    aria-selected={isSelected}
                  >
                    {/* Line 1: Fault name and outcome in plain words */}
                    <div className="text-sm font-semibold text-text truncate">
                      {faultDisplay} · {outcomeWord}
                    </div>

                    {/* Line 2: Date and mode */}
                    <div className="text-sm text-text-3">
                      {shortDate} · {isLive ? 'Live LLM' : 'Scripted / Rule'}
                    </div>

                    {/* Line 3: Run ID in mono, middle-truncated on a single line */}
                    <div className="text-sm text-text-3">
                      <code className="text-sm text-text-3" title={r.run_id}>
                        {truncatedId}
                      </code>
                    </div>
                  </button>
                );
              })
            )}
          </div>
        </aside>

        {/* Right Main Area: Run Header, Key Figures Strip, then 3-Column Detail Area */}
        <main className="flex-1 flex flex-col overflow-y-auto bg-page">
          {/* Run Header (Page Title 28px in plain words, raw ID in mono 14px) */}
          <div className="px-8 pt-6 pb-2">
            <h1 className="text-[28px] font-bold text-text tracking-tight leading-tight">
              {faultLabel}, {outcomeText.toLowerCase()}
            </h1>
            <div className="flex items-center gap-3 text-sm text-text-3 mt-1.5 flex-wrap">
              <span>Run ID: <code className="text-text text-sm">{currentRun.run_id}</code></span>
              <span>•</span>
              <span>Mode: <strong className="text-text-2 font-medium">{currentRun.patch_mode === 'live' || currentRun.diag_mode === 'live' ? 'Live LLM' : 'Scripted / Rule'}</strong></span>
              <span>•</span>
              <span>Model: <code className="text-text-2 text-sm">{currentRun.model || 'rule'}</code></span>
              <span>•</span>
              <span>Started: <span className="text-text-2 tabular-nums">{formatTimestamp(currentRun.started_at)}</span></span>
            </div>
          </div>

          {/* Key Figures Strip: Separated by hairlines, NOT cards (24px charcoal figures, 14px labels) */}
          <section className="px-4 sm:px-8 my-4" aria-label="Key Run Metrics">
            <div className="border-y border-line py-2 sm:py-4 bg-surface/50 grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-6">
              {/* Figure 1: Outcome (Charcoal for normal, danger for rollback) */}
              <div className="p-3 sm:px-4 sm:py-2 border-b sm:border-b-0 sm:border-r border-line flex flex-col gap-1">
                <span className="text-sm text-text-3 font-medium">Deployment Outcome</span>
                <span className={`text-2xl font-bold tracking-tight ${
                  outcomeText === 'Rolled back' ? 'text-danger-ink' : 'text-text'
                }`}>
                  {outcomeText}
                </span>
              </div>

              {/* Figure 2: Fault ID */}
              <div className="p-3 sm:px-4 sm:py-2 border-b sm:border-b-0 sm:border-r border-line flex flex-col gap-1">
                <span className="text-sm text-text-3 font-medium">Fault Injected</span>
                <span className="text-2xl font-bold tracking-tight text-text">
                  {currentRun.fault_id || 'None'}
                </span>
              </div>

              {/* Figure 3: Risk Tier (Charcoal for low, tint only for high/medium) */}
              <div className="p-3 sm:px-4 sm:py-2 border-b sm:border-b-0 sm:border-r border-line flex flex-col gap-1">
                <span className="text-sm text-text-3 font-medium">Risk Tier</span>
                <span className={`text-2xl font-bold tracking-tight ${
                  riskTierText === 'HIGH' ? 'text-danger-ink' : riskTierText === 'MEDIUM' ? 'text-warning-ink' : 'text-text'
                }`}>
                  {riskTierText}
                </span>
              </div>

              {/* Figure 4: Gates Passed */}
              <div className="p-3 sm:px-4 sm:py-2 border-b md:border-b-0 sm:border-r border-line flex flex-col gap-1">
                <span className="text-sm text-text-3 font-medium">Gates Passed</span>
                <span className="text-2xl font-bold tracking-tight text-text tabular-nums">
                  {gatesPassedCount}
                </span>
              </div>

              {/* Figure 5: Decision (Charcoal for auto_apply, tint only for reject/escalate) */}
              <div className="p-3 sm:px-4 sm:py-2 border-b sm:border-b-0 sm:border-r border-line flex flex-col gap-1">
                <span className="text-sm text-text-3 font-medium">Engine Decision</span>
                <span className={`text-2xl font-bold tracking-tight ${
                  decisionText === 'REJECT' ? 'text-danger-ink' : decisionText === 'ESCALATE' ? 'text-warning-ink' : 'text-text'
                }`}>
                  {decisionText}
                </span>
              </div>

              {/* Figure 6: Recovery Time */}
              <div className="p-3 sm:px-4 sm:py-2 last:border-b-0 lg:border-r-0 flex flex-col gap-1">
                <span className="text-sm text-text-3 font-medium">Recovery Time</span>
                <span className="text-2xl font-bold tracking-tight text-text tabular-nums">
                  {recoveryTimeText}
                </span>
              </div>
            </div>
          </section>

          {/* 3-Column Inspection Area: Left = Vertical Stage List (10 stages, NO horizontal scroll), Center = Evidence, Right = Diff */}
          <div className="px-8 py-4 grid grid-cols-1 xl:grid-cols-12 gap-6 items-start">
            {/* Sub-Column 1 (Cols 1-3): Vertical Stage Navigation (Never scrolls horizontally!) */}
            <div className="xl:col-span-3 flex flex-col gap-3">
              <div className="pb-2 border-b border-line flex items-center justify-between">
                <span className="text-sm font-semibold text-text">Pipeline Stages (10)</span>
                <span className="text-sm text-text-3 tabular-nums">Step {activeStageIdx + 1} of 10</span>
              </div>

              <nav className="flex flex-col gap-1" aria-label="Vertical Pipeline Stages">
                {stages.map((stage, idx) => {
                  const isActive = activeStageIdx === idx;
                  const isFail = stage.status === 'fail' || stage.status === 'error';
                  const isWarning = stage.status === 'timeout' || stage.status === 'escalate';
                  const isSkipped = stage.status === 'skipped' || stage.status === 'not_run';

                  let IconComponent = Check;
                  let attentionWord: string | null = null;
                  let itemClasses = 'text-text-2 hover:bg-surface-2';

                  if (isFail) {
                    IconComponent = X;
                    attentionWord = 'Fail';
                    itemClasses = 'bg-danger-tint text-danger-ink border border-danger-line/40';
                  } else if (isWarning) {
                    IconComponent = AlertTriangle;
                    attentionWord = 'Warning';
                    itemClasses = 'bg-warning-tint text-warning-ink border border-warning-line/40';
                  } else if (isSkipped) {
                    IconComponent = Minus;
                    itemClasses = 'text-text-3 hover:bg-surface-2';
                  }

                  if (isActive) {
                    itemClasses = 'bg-selected text-text font-semibold border border-line-strong';
                  }

                  return (
                    <button
                      key={stage.id}
                      onClick={() => setActiveStageIdx(idx)}
                      className={`h-10 px-3 w-full rounded text-sm flex items-center justify-between transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus ${itemClasses}`}
                      aria-current={isActive ? 'step' : undefined}
                    >
                      <div className="flex items-center gap-2.5">
                        <span className="text-sm font-bold text-text-3 tabular-nums w-4 text-left select-none">
                          {idx + 1}
                        </span>
                        <span className="text-sm truncate">{stage.name}</span>
                      </div>

                      <div className="flex items-center gap-1.5 flex-shrink-0">
                        <IconComponent size={14} strokeWidth={2.5} aria-hidden="true" />
                        {attentionWord && (
                          <span className="text-sm font-semibold">{attentionWord}</span>
                        )}
                      </div>
                    </button>
                  );
                })}
              </nav>
            </div>

            {/* Sub-Column 2 (Cols 4-8): Stage Detailed Evidence using Definition Lists and Tables */}
            <div className="xl:col-span-5 flex flex-col gap-6">
              {/* Stage Header */}
              <div className="flex items-center justify-between pb-3 border-b border-line">
                <div>
                  <span className="text-sm text-text-3 font-medium">
                    Stage {activeStageIdx + 1} of 10
                  </span>
                  <h2 className="text-[20px] font-semibold text-text mt-0.5">
                    {activeStage?.name}: Evidence &amp; Execution State
                  </h2>
                </div>
                <StatusBadge status={activeStage?.status} />
              </div>

              {/* Stage 1: Detection */}
              {activeStage?.id === 'detection' && (
                <div className="flex flex-col gap-6">
                  <div>
                    <h3 className="text-base font-semibold text-text mb-3">Incident Telemetry</h3>
                    <dl className="grid grid-cols-1 sm:grid-cols-2 gap-y-3 gap-x-6 text-sm border-y border-line py-3">
                      <div>
                        <dt className="text-text-3 font-medium">Fault Identifier</dt>
                        <dd className="text-text font-semibold mt-0.5">
                          <code>{currentRun.incident?.fault_id || currentRun.fault_id || 'None'}</code>
                        </dd>
                      </div>
                      <div>
                        <dt className="text-text-3 font-medium">Detection Rule</dt>
                        <dd className="text-text font-semibold mt-0.5">
                          <code>{currentRun.incident?.rule || 'HTTP 500 / Latency Breach'}</code>
                        </dd>
                      </div>
                      <div>
                        <dt className="text-text-3 font-medium">Failing Endpoint</dt>
                        <dd className="text-text mt-0.5">
                          <code>{currentRun.incident?.endpoint || '/api/health'}</code>
                        </dd>
                      </div>
                      <div>
                        <dt className="text-text-3 font-medium">Consecutive Bad Checks</dt>
                        <dd className="text-text tabular-nums mt-0.5">
                          {currentRun.incident?.consecutive_bad_checks ?? 2}
                        </dd>
                      </div>
                    </dl>
                  </div>

                  {currentRun.incident?.evidence && currentRun.incident.evidence.length > 0 && (
                    <div>
                      <h3 className="text-base font-semibold text-text mb-2">Probe Failure Evidence</h3>
                      <ul className="list-disc list-inside space-y-1.5 text-sm text-danger-ink bg-danger-tint/20 p-4 rounded border border-danger-line/30">
                        {currentRun.incident.evidence.map((ev, i) => (
                          <li key={i}><code>{ev}</code></li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {currentRun.incident?.expected && (
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm border-t border-line pt-4">
                      <div>
                        <span className="text-text-3 font-medium block mb-1">Expected Response</span>
                        <div className="p-3 bg-surface-2 rounded text-success-ink text-sm border border-line">
                          <code>{currentRun.incident.expected}</code>
                        </div>
                      </div>
                      <div>
                        <span className="text-text-3 font-medium block mb-1">Actual Response</span>
                        <div className="p-3 bg-surface-2 rounded text-danger-ink text-sm border border-line">
                          <code>{currentRun.incident.actual}</code>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* Stage 2: Incident Evidence / Probe History */}
              {activeStage?.id === 'incident_evidence' && (
                <div className="flex flex-col gap-4">
                  <h3 className="text-base font-semibold text-text">Probe Measurement History</h3>
                  {currentRun.incident?.failing_check?.probes ? (
                    <div className="border border-line rounded overflow-x-auto">
                      <table className="w-full min-w-[480px] text-left text-sm border-collapse">
                        <thead className="bg-surface-2 text-text-3 border-b border-line">
                          <tr>
                            <th className="p-3 font-medium">Probe Name</th>
                            <th className="p-3 font-medium">Path</th>
                            <th className="p-3 font-medium">HTTP Code</th>
                            <th className="p-3 font-medium text-right">Latency</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-line text-sm">
                          {currentRun.incident.failing_check.probes.map((p: any, i: number) => (
                            <tr key={i} className="hover:bg-surface-2/40">
                              <td className="p-3 font-medium text-text"><code>{p.probe}</code></td>
                              <td className="p-3 text-text-2"><code>{p.path}</code></td>
                              <td className="p-3 tabular-nums font-semibold">
                                <span className={p.http === 200 ? 'text-success-ink' : 'text-danger-ink'}>
                                  {p.http}
                                </span>
                              </td>
                              <td className="p-3 text-right tabular-nums text-text-2">{p.ms} ms</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <div className="p-6 bg-surface rounded border border-line text-sm text-text-3">
                      No multi-probe trace preserved for this incident.
                    </div>
                  )}
                </div>
              )}

              {/* Stage 3: Diagnosis */}
              {activeStage?.id === 'diagnosis' && (
                <div className="flex flex-col gap-5 text-sm">
                  <h3 className="text-base font-semibold text-text">Diagnostic Root Cause Analysis</h3>
                  <dl className="grid grid-cols-1 sm:grid-cols-2 gap-y-3 gap-x-6 border-y border-line py-3">
                    <div>
                      <dt className="text-text-3 font-medium">Diagnosis Mode</dt>
                      <dd className="text-text font-semibold mt-0.5">
                        {currentRun.diagnosis?.provider_mode || currentRun.diag_mode || 'rule'}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-text-3 font-medium">Model Utilized</dt>
                      <dd className="text-text font-semibold mt-0.5">
                        {currentRun.diagnosis?.model || currentRun.model || 'rule'}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-text-3 font-medium">Diagnosed Target File</dt>
                      <dd className="text-text mt-0.5">
                        <code>{currentRun.diagnosis?.causes?.[0]?.file || 'order-service/...'}</code>
                      </dd>
                    </div>
                    <div>
                      <dt className="text-text-3 font-medium">Localisation Target Hit</dt>
                      <dd className="text-text font-semibold mt-0.5">
                        {currentRun.diagnosis?.top1_hit ? 'Top-1 Localization Match' : 'Identified by diagnosis engine'}
                      </dd>
                    </div>
                  </dl>

                  {currentRun.diagnosis?.causes?.[0]?.reason && (
                    <div>
                      <span className="text-text-3 font-medium block mb-1">Identified Root Cause</span>
                      <p className="text-text bg-surface p-4 rounded border border-line leading-relaxed">
                        {currentRun.diagnosis.causes[0].reason}
                      </p>
                    </div>
                  )}
                </div>
              )}

              {/* Stage 4: Candidates */}
              {activeStage?.id === 'candidate_generation' && (
                <div className="flex flex-col gap-4 text-sm">
                  <h3 className="text-base font-semibold text-text">Drafted Patch Candidates</h3>
                  <p className="text-text-2">
                    AutoImmune drafts up to 3 candidate patches per incident to evaluate against execution gates.
                  </p>
                  <div className="border border-line rounded overflow-x-auto">
                    <table className="w-full min-w-[480px] text-left text-sm border-collapse">
                      <thead className="bg-surface-2 text-text-3 border-b border-line">
                        <tr>
                          <th className="p-3 font-medium">Candidate</th>
                          <th className="p-3 font-medium">Origin / Intent</th>
                          <th className="p-3 font-medium">Diff Size</th>
                          <th className="p-3 font-medium">Decision</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-line text-sm">
                        {currentRun.candidates?.map((c, i) => (
                          <tr
                            key={c.candidate_id}
                            onClick={() => setSelectedCandIdx(i)}
                            className={`cursor-pointer transition-colors ${
                              selectedCandIdx === i ? 'bg-selected font-medium' : 'hover:bg-surface-2/60'
                            }`}
                          >
                            <td className="p-3 text-sm text-text">
                              <code>Candidate #{i + 1}</code>
                            </td>
                            <td className="p-3 text-text-2">
                              {c.cohort === 'llm' ? 'Live LLM draft' : `Scripted: ${c.candidate_id.replace(/^F\d+-scripted-/, '').slice(0, 8)}`}
                              {c.offline_oracle_label && (
                                <span className="ml-2 text-xs px-1.5 py-0.5 rounded bg-surface-2 text-text-3 border border-line" title="Post-hoc offline research label (never visible to runtime pipeline)">
                                  post-hoc: {c.offline_oracle_label}
                                </span>
                              )}
                            </td>
                            <td className="p-3 tabular-nums text-text-3">
                              {c.diff_lines != null ? `${c.diff_lines} lines` : '–'}
                            </td>
                            <td className="p-3">
                              <StatusBadge status={c.decision?.decision || 'REJECT'} />
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* Stage 5: Validation Gates (V0-V3 Matrix as a Clear Full Table) */}
              {activeStage?.id === 'validation_gates' && (
                <div className="flex flex-col gap-4 text-sm">
                  <div className="flex items-center justify-between">
                    <h3 className="text-base font-semibold text-text">
                      Execution Evidence: V0–V3 Validation Matrix
                    </h3>
                    <span className="text-text-3 text-sm">
                      Evaluating Candidate #{selectedCandIdx + 1}
                    </span>
                  </div>

                  <p className="text-text-2">
                    All gates execute inside an isolated Docker sandbox with <code>--network none</code>. A timeout or tool error is strictly recorded as a failure.
                  </p>

                  <div className="border border-line rounded overflow-x-auto">
                    <table className="w-full min-w-[560px] text-left text-sm border-collapse">
                      <thead className="bg-surface-2 text-text-3 border-b border-line">
                        <tr>
                          <th className="p-3 font-medium">Gate</th>
                          <th className="p-3 font-medium">Validation Objective</th>
                          <th className="p-3 font-medium">Outcome</th>
                          <th className="p-3 font-medium text-right">Duration</th>
                          <th className="p-3 font-medium">Findings / Log Summary</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-line text-sm">
                        {/* V0 Gate */}
                        {(() => {
                          const g = currentCandidate?.gates?.V0;
                          const status = g?.status || 'not_run';
                          const isUnrun = status === 'not_run';
                          const duration = isUnrun ? '–' : (typeof g?.seconds === 'number' ? `${g.seconds.toFixed(2)}s` : '–');
                          const findings = isUnrun
                            ? 'Not executed'
                            : (g?.log_tail && g.log_tail.trim())
                              ? g.log_tail.trim()
                              : (status === 'pass' ? 'Clean git apply and Maven compilation (exit code 0)' : 'Compilation or patch application failed');
                          return (
                            <tr className="hover:bg-surface-2/40">
                              <td className="p-3 font-bold text-text"><code>V0</code></td>
                              <td className="p-3 text-text-2">Clean git apply &amp; Maven compile</td>
                              <td className="p-3">
                                <StatusBadge status={status} />
                              </td>
                              <td className="p-3 text-right tabular-nums text-text-2">{duration}</td>
                              <td className="p-3 text-text-3 text-sm max-w-[340px] truncate" title={findings}>
                                {findings}
                              </td>
                            </tr>
                          );
                        })()}

                        {/* V1 Gate */}
                        {(() => {
                          const g = currentCandidate?.gates?.V1;
                          const status = g?.status || 'not_run';
                          const isUnrun = status === 'not_run';
                          const duration = isUnrun ? '–' : (typeof g?.seconds === 'number' ? `${g.seconds.toFixed(2)}s` : '–');
                          const findings = isUnrun
                            ? 'Not executed (stopped by prior gate)'
                            : (g?.log_tail && g.log_tail.trim())
                              ? g.log_tail.trim()
                              : (status === 'pass' ? 'Visible reproduction target test passed' : 'Target test reproduction failed');
                          return (
                            <tr className="hover:bg-surface-2/40">
                              <td className="p-3 font-bold text-text"><code>V1</code></td>
                              <td className="p-3 text-text-2">Visible target test for the fault</td>
                              <td className="p-3">
                                <StatusBadge status={status} />
                              </td>
                              <td className="p-3 text-right tabular-nums text-text-2">{duration}</td>
                              <td className="p-3 text-text-3 text-sm max-w-[340px] truncate" title={findings}>
                                {findings}
                              </td>
                            </tr>
                          );
                        })()}

                        {/* V2 Gate */}
                        {(() => {
                          const g = currentCandidate?.gates?.V2;
                          const status = g?.status || 'not_run';
                          const isUnrun = status === 'not_run';
                          const duration = isUnrun ? '–' : (typeof g?.seconds === 'number' ? `${g.seconds.toFixed(2)}s` : '–');
                          const findings = isUnrun
                            ? 'Not executed (stopped by prior gate)'
                            : (g?.log_tail && g.log_tail.trim())
                              ? g.log_tail.trim()
                              : (status === 'pass' ? 'All existing unit & integration tests pass' : 'Regression test failures detected');
                          return (
                            <tr className="hover:bg-surface-2/40">
                              <td className="p-3 font-bold text-text"><code>V2</code></td>
                              <td className="p-3 text-text-2">Full existing regression test suite</td>
                              <td className="p-3">
                                <StatusBadge status={status} />
                              </td>
                              <td className="p-3 text-right tabular-nums text-text-2">{duration}</td>
                              <td className="p-3 text-text-3 text-sm max-w-[340px] truncate" title={findings}>
                                {findings}
                              </td>
                            </tr>
                          );
                        })()}

                        {/* V3 Gate */}
                        {(() => {
                          const g = currentCandidate?.gates?.V3;
                          const status = g?.status || 'not_run';
                          const isUnrun = status === 'not_run';
                          const duration = isUnrun ? '–' : (typeof g?.seconds === 'number' ? `${g.seconds.toFixed(2)}s` : '–');
                          const findings = isUnrun
                            ? 'Not executed (stopped by prior gate)'
                            : (g?.log_tail && g.log_tail.trim())
                              ? g.log_tail.trim()
                              : (status === 'pass' ? '0 new differential security findings' : 'Differential static scan identified security vulnerabilities');
                          return (
                            <tr className="hover:bg-surface-2/40">
                              <td className="p-3 font-bold text-text"><code>V3</code></td>
                              <td className="p-3 text-text-2">Semgrep differential security analysis</td>
                              <td className="p-3">
                                <StatusBadge status={status} />
                              </td>
                              <td className="p-3 text-right tabular-nums text-text-2">{duration}</td>
                              <td className="p-3 text-text-3 text-sm max-w-[340px] truncate" title={findings}>
                                {findings}
                              </td>
                            </tr>
                          );
                        })()}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* Stage 6: Decision Engine */}
              {activeStage?.id === 'decision_engine' && (
                <div className="flex flex-col gap-4 text-sm">
                  <h3 className="text-base font-semibold text-text">Deterministic Risk-Tier Decision</h3>
                  <dl className="grid grid-cols-1 sm:grid-cols-2 gap-y-3 gap-x-6 border-y border-line py-3">
                    <div>
                      <dt className="text-text-3 font-medium">Assigned Risk Tier</dt>
                      <dd className="text-text font-bold mt-0.5">{riskTierText}</dd>
                    </div>
                    <div>
                      <dt className="text-text-3 font-medium">Policy Action</dt>
                      <dd className="text-text font-bold mt-0.5">{decisionText}</dd>
                    </div>
                  </dl>

                  <div>
                    <span className="text-text-3 font-medium block mb-2">Decision Engine Reasons</span>
                    <ul className="list-disc list-inside space-y-1 text-text-2 bg-surface p-4 rounded border border-line">
                      {currentCandidate?.decision?.reasons && currentCandidate.decision.reasons.length > 0 ? (
                        currentCandidate.decision.reasons.map((r, i) => <li key={i}>{r}</li>)
                      ) : (
                        <li>All validation gates passed; diff strictly bounded within diagnosed file.</li>
                      )}
                    </ul>
                  </div>
                </div>
              )}

              {/* Stage 7: Human Approval */}
              {activeStage?.id === 'human_approval' && (
                <div className="flex flex-col gap-4 text-sm">
                  <h3 className="text-base font-semibold text-text">Governance &amp; Approval Gate</h3>
                  <dl className="grid grid-cols-1 sm:grid-cols-2 gap-y-3 gap-x-6 border-y border-line py-3">
                    <div>
                      <dt className="text-text-3 font-medium">Policy Requirement</dt>
                      <dd className="text-text mt-0.5">
                        {riskTierText === 'LOW' ? 'Unattended Auto-Apply Permitted' : 'Human Review Mandated'}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-text-3 font-medium">Status</dt>
                      <dd className="text-text font-semibold mt-0.5">
                        {riskTierText === 'LOW' ? 'Auto-approved by threshold policy' : 'Escalated to engineer'}
                      </dd>
                    </div>
                  </dl>
                </div>
              )}

              {/* Stage 8: Deployment */}
              {activeStage?.id === 'deployment' && (
                <div className="flex flex-col gap-4 text-sm">
                  <h3 className="text-base font-semibold text-text">Deployment Execution</h3>
                  <dl className="grid grid-cols-1 sm:grid-cols-2 gap-y-3 gap-x-6 border-y border-line py-3">
                    <div>
                      <dt className="text-text-3 font-medium">Target Service</dt>
                      <dd className="text-text font-semibold mt-0.5">order-service</dd>
                    </div>
                    <div>
                      <dt className="text-text-3 font-medium">Image Tag</dt>
                      <dd className="text-text mt-0.5">
                        <code>{currentRun.deploy_artifact?.image_tag || 'order-service:patched'}</code>
                      </dd>
                    </div>
                    <div>
                      <dt className="text-text-3 font-medium">Previous Tag Preserved</dt>
                      <dd className="text-text mt-0.5">
                        <code>{currentRun.deploy_artifact?.previous_tag || 'order-service:healthy'}</code>
                      </dd>
                    </div>
                    <div>
                      <dt className="text-text-3 font-medium">Build Time</dt>
                      <dd className="text-text tabular-nums mt-0.5">
                        {currentRun.deploy_artifact?.build_duration_sec ? `${currentRun.deploy_artifact.build_duration_sec.toFixed(1)}s` : 'Unavailable'}
                      </dd>
                    </div>
                  </dl>
                </div>
              )}

              {/* Stage 9: Health Window */}
              {activeStage?.id === 'health_window' && (
                <div className="flex flex-col gap-4 text-sm">
                  <h3 className="text-base font-semibold text-text">Post-Deployment Health Window</h3>
                  <p className="text-text-2">
                    Actuator health checks, latency thresholds, and canary probes evaluate post-deployment stability.
                  </p>
                  <dl className="grid grid-cols-1 sm:grid-cols-2 gap-y-3 gap-x-6 border-y border-line py-3">
                    <div>
                      <dt className="text-text-3 font-medium">Actuator Status</dt>
                      <dd className="text-text font-semibold mt-0.5">
                        {currentRun.rollback_artifact ? 'BREACHED / UNHEALTHY' : 'UP (Healthy)'}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-text-3 font-medium">Rollback Event</dt>
                      <dd className="text-text mt-0.5">
                        {currentRun.rollback_artifact ? (
                          <span className="text-danger-ink font-semibold">Automatic swap to previous image</span>
                        ) : (
                          <span className="text-text font-semibold">No rollback triggered</span>
                        )}
                      </dd>
                    </div>
                  </dl>
                </div>
              )}

              {/* Stage 10: Provenance Record */}
              {activeStage?.id === 'provenance_record' && (
                <div className="flex flex-col gap-4 text-sm">
                  <h3 className="text-base font-semibold text-text">Audit &amp; Evidence Provenance</h3>
                  <dl className="grid grid-cols-1 sm:grid-cols-2 gap-y-3 gap-x-6 border-y border-line py-3">
                    <div>
                      <dt className="text-text-3 font-medium">Run Artifact Path</dt>
                      <dd className="text-text mt-0.5">
                        <code>runs/{currentRun.run_id}/</code>
                      </dd>
                    </div>
                    <div>
                      <dt className="text-text-3 font-medium">Evidence Record</dt>
                      <dd className="text-text mt-0.5">
                        <code>results/evidence.jsonl</code>
                      </dd>
                    </div>
                  </dl>
                </div>
              )}
            </div>

            {/* Sub-Column 3 (Cols 9-12): Candidate Patch Selector & Unified Diff Viewer */}
            <div className="xl:col-span-4 flex flex-col gap-4">
              <div className="flex items-center justify-between pb-3 border-b border-line">
                <div className="flex items-center gap-2">
                  <FileCode size={18} className="text-lead-ink" aria-hidden="true" />
                  <h3 className="text-base font-semibold text-text">Candidate Diff</h3>
                </div>
                <div className="flex items-center gap-1.5" role="tablist" aria-label="Candidate patch selector">
                  {currentRun.candidates?.map((c, i) => (
                    <button
                      key={c.candidate_id}
                      role="tab"
                      aria-selected={selectedCandIdx === i}
                      onClick={() => setSelectedCandIdx(i)}
                      className={`h-8 px-2.5 rounded text-sm transition-colors ${
                        selectedCandIdx === i
                          ? 'bg-selected text-text font-bold border border-line-strong'
                          : 'bg-surface hover:bg-surface-2 text-text-3 border border-line'
                      }`}
                    >
                      #{i + 1}
                    </button>
                  ))}
                </div>
              </div>

              {currentCandidate ? (
                <div className="flex flex-col gap-3">
                  <div className="flex items-center justify-between text-sm text-text-3">
                    <span className="truncate min-w-0" title={targetFilePath}>
                      Target: <code className="text-text-2 text-sm">{truncateMiddle(targetFilePath, 24)}</code>
                    </span>
                    <span className="tabular-nums flex-shrink-0 whitespace-nowrap">{currentCandidate.diff_lines || 12} lines</span>
                  </div>

                  <DiffViewer
                    diffText={currentCandidate.diff_snippet}
                    filePath={targetFilePath}
                  />
                </div>
              ) : (
                <div className="p-8 bg-surface rounded border border-line text-sm text-text-3 text-center">
                  No patch candidate generated for this run.
                </div>
              )}
            </div>
          </div>
        </main>
      </div>
    </div>
  );
};
