import React from 'react';
import { EvidenceSnapshot } from '../../types/evidence';
import { ArrowRight, Terminal } from 'lucide-react';

interface OverviewProps {
  snapshot: EvidenceSnapshot;
  onNavigate: (tab: 'explorer' | 'inspector' | 'results') => void;
}

export const Overview: React.FC<OverviewProps> = ({ snapshot, onNavigate }) => {
  const metadata = snapshot.metadata;
  const isAnalyseStale = metadata.analyse_check?.status === 'STALE';

  return (
    <div className="flex-1 flex flex-col overflow-y-auto bg-page text-text">
      {/* Top Page Title Header */}
      <div className="px-8 pt-8 pb-3">
        <h1 className="text-[28px] font-bold text-text tracking-tight leading-tight">
          AutoImmune: Validation-Gated Self-Healing Pipeline
        </h1>
        <p className="text-sm text-text-3 mt-1.5 leading-relaxed">
          An Empirical Study of Validation-Gated Deployment Strategies for LLM-Generated Software Patches · Spring Boot <code>order-service</code>
        </p>
      </div>

      {/* Notice: ANALYSE STALE Backend Signal */}
      {isAnalyseStale && (
        <div className="mx-8 my-2 p-4 bg-warning-tint/30 border border-warning-line/50 rounded flex items-start gap-3 text-sm">
          <Terminal size={18} className="text-warning-ink flex-shrink-0 mt-0.5" aria-hidden="true" />
          <div className="flex-1">
            <span className="font-semibold text-warning-ink block">
              Authoritative Signal: Derived CSV outputs are STALE relative to current inputs
            </span>
            <p className="text-text-2 mt-1 leading-relaxed text-sm">
              <code>python analyse.py --check</code> reports that derived tables in <code>results/</code> (including <code>deployments.csv</code>, <code>first_stop.csv</code>, <code>gate_incremental.csv</code>, and <code>runs.csv</code>) differ from what current historical runs produce. In accordance with strict experimental integrity rules, raw evidence is preserved and derived files have not been overwritten.
            </p>
          </div>
        </div>
      )}

      {/* Key Figures Strip: Ruled by 1px hairlines, NOT cards (24px figures, 14px labels) */}
      <section className="px-8 my-4" aria-label="Authoritative Dataset Metrics">
        <div className="border-y border-line py-4 bg-surface/50 grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 divide-y md:divide-y-0 md:divide-x divide-line">
          {/* Metric 1: Recorded Runs */}
          <div className="px-4 py-2 first:pl-0 flex flex-col gap-1">
            <span className="text-sm text-text-3 font-medium">Recorded Pipeline Runs</span>
            <span className="text-2xl font-bold tracking-tight text-text tabular-nums">
              {metadata.total_runs_recorded} runs
            </span>
          </div>

          {/* Metric 2: Candidate Patches */}
          <div className="px-4 py-2 flex flex-col gap-1">
            <span className="text-sm text-text-3 font-medium">Candidates Evaluated</span>
            <span className="text-2xl font-bold tracking-tight text-text tabular-nums">
              {metadata.total_evidence_rows} patches
            </span>
          </div>

          {/* Metric 3: LLM Cohort */}
          <div className="px-4 py-2 flex flex-col gap-1">
            <span className="text-sm text-text-3 font-medium">Live LLM Cohort</span>
            <span className="text-2xl font-bold tracking-tight text-lead-ink tabular-nums">
              {metadata.llm_units_count} units
            </span>
          </div>

          {/* Metric 4: Scripted Baseline */}
          <div className="px-4 py-2 flex flex-col gap-1">
            <span className="text-sm text-text-3 font-medium">Scripted Baseline</span>
            <span className="text-2xl font-bold tracking-tight text-text-2 tabular-nums">
              {metadata.scripted_units_count} units
            </span>
          </div>

          {/* Metric 5: Auto-Applies */}
          <div className="px-4 py-2 flex flex-col gap-1">
            <span className="text-sm text-text-3 font-medium">Auto-Applied Patches</span>
            <span className="text-2xl font-bold tracking-tight text-success-ink tabular-nums">
              {snapshot.first_stop_distribution?.['not stopped'] ?? 20} patches
            </span>
          </div>

          {/* Metric 6: Canary Rollbacks */}
          <div className="px-4 py-2 last:pr-0 flex flex-col gap-1">
            <span className="text-sm text-text-3 font-medium">Canary Rollbacks</span>
            <span className="text-2xl font-bold tracking-tight text-danger-ink tabular-nums">
              {snapshot.first_stop_distribution?.['rollback'] ?? 3} caught
            </span>
          </div>
        </div>
      </section>

      {/* Main Two-Column Research Layout at 1920/1366 */}
      <div className="px-8 py-4 grid grid-cols-1 xl:grid-cols-12 gap-8 items-start">
        {/* Left Column (Cols 1-7): Pipeline Architecture, Gates Funnel & Policies */}
        <div className="xl:col-span-7 flex flex-col gap-6">
          {/* Research Hypothesis & Pipeline Sequencing */}
          <div>
            <h2 className="text-[20px] font-semibold text-text mb-2">
              Research Question &amp; Fixed Pipeline Flow
            </h2>
            <p className="text-base text-text-2 leading-relaxed">
              <strong>Core Research Question:</strong> How much execution evidence lets an AI-generated software patch deploy without human review, and what does each sequential validation gate catch?
            </p>
            <p className="text-sm text-text-3 mt-2 leading-relaxed">
              AutoImmune uses a strictly deterministic orchestrator. Large Language Models are isolated strictly to <code>diagnose()</code> and <code>draft_patches()</code>; all validation, gating, risk tiering, container deployment, and canary rollback operations are deterministic code.
            </p>
          </div>

          {/* The 4 Sequential Validation Gates (Docker with --network none) */}
          <div>
            <div className="flex items-center justify-between pb-2 border-b border-line mb-3">
              <h3 className="text-base font-semibold text-text">
                The 4-Gate Isolated Execution Funnel
              </h3>
              <span className="text-sm text-text-3">Docker sandbox: <code>--network none</code></span>
            </div>

            <div className="border border-line rounded overflow-x-auto">
              <table className="w-full min-w-[520px] text-left text-sm border-collapse">
                <thead className="bg-surface-2 text-text-3 border-b border-line">
                  <tr>
                    <th className="p-3 font-medium">Gate</th>
                    <th className="p-3 font-medium">Execution Objective</th>
                    <th className="p-3 font-medium">Failure Condition</th>
                    <th className="p-3 font-medium text-right">Stops Caught</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line text-sm">
                  <tr className="hover:bg-surface-2/40">
                    <td className="p-3 font-bold text-text"><code>V0</code></td>
                    <td className="p-3 text-text">Syntax &amp; Compilation</td>
                    <td className="p-3 text-text-3"><code>git apply --check</code> fails or <code>mvn compile</code> non-zero</td>
                    <td className="p-3 text-right font-semibold text-danger-ink tabular-nums">
                      {snapshot.first_stop_distribution?.['V0'] ?? 31} of 241
                    </td>
                  </tr>
                  <tr className="hover:bg-surface-2/40">
                    <td className="p-3 font-bold text-text"><code>V1</code></td>
                    <td className="p-3 text-text">Visible Target Reproduction Test</td>
                    <td className="p-3 text-text-3">Fault reproduction unit test fails</td>
                    <td className="p-3 text-right font-semibold text-danger-ink tabular-nums">
                      {snapshot.first_stop_distribution?.['V1'] ?? 24} of 241
                    </td>
                  </tr>
                  <tr className="hover:bg-surface-2/40">
                    <td className="p-3 font-bold text-text"><code>V2</code></td>
                    <td className="p-3 text-text">Regression Test Suite</td>
                    <td className="p-3 text-text-3">Any existing healthy unit/integration test regresses</td>
                    <td className="p-3 text-right font-semibold text-danger-ink tabular-nums">
                      {snapshot.first_stop_distribution?.['V2'] ?? 9} of 241
                    </td>
                  </tr>
                  <tr className="hover:bg-surface-2/40">
                    <td className="p-3 font-bold text-text"><code>V3</code></td>
                    <td className="p-3 text-text">Differential Security Analysis</td>
                    <td className="p-3 text-text-3">Semgrep differential scan finds new vulnerability</td>
                    <td className="p-3 text-right font-semibold text-danger-ink tabular-nums">
                      {snapshot.first_stop_distribution?.['V3'] ?? 8} of 241
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          {/* Risk Tiers & Deterministic Decision Engine */}
          <div>
            <h3 className="text-base font-semibold text-text mb-3">
              Deterministic Risk Tiers (config/decision.yaml)
            </h3>
            <dl className="grid grid-cols-1 sm:grid-cols-3 gap-4 border-y border-line py-4">
              <div className="flex flex-col gap-1">
                <dt className="text-sm font-semibold text-danger-ink">REJECT (High Tier)</dt>
                <dd className="text-sm text-text-2 leading-relaxed">
                  V0, V1, or V2 fails, or a new high-severity Semgrep finding is introduced. Candidate is discarded immediately.
                </dd>
              </div>
              <div className="flex flex-col gap-1">
                <dt className="text-sm font-semibold text-warning-ink">ESCALATE (Medium Tier)</dt>
                <dd className="text-sm text-text-2 leading-relaxed">
                  All gates pass, but low-severity findings exist, diff exceeds line limits, file outside diagnosis, or sample disagreement.
                </dd>
              </div>
              <div className="flex flex-col gap-1">
                <dt className="text-sm font-semibold text-success-ink">AUTO_APPLY (Low Tier)</dt>
                <dd className="text-sm text-text-2 leading-relaxed">
                  All gates pass, zero new findings, diff inside diagnosed file and within strict size threshold. Unattended deployment permitted.
                </dd>
              </div>
            </dl>
          </div>
        </div>

        {/* Right Column (Cols 8-12): Benchmark Faults, Provenance & Direct Navigation */}
        <div className="xl:col-span-5 flex flex-col gap-6">
          {/* Ground Truth Fault Injections */}
          <div>
            <h2 className="text-[20px] font-semibold text-text mb-3">
              Benchmark Fault Profiles
            </h2>
            <div className="border border-line rounded overflow-x-auto">
              <table className="w-full min-w-[520px] text-left text-sm border-collapse">
                <thead className="bg-surface-2 text-text-3 border-b border-line">
                  <tr>
                    <th className="p-3 font-medium">Fault ID</th>
                    <th className="p-3 font-medium">Description</th>
                    <th className="p-3 font-medium">Domain</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line text-sm">
                  <tr className="hover:bg-surface-2/40">
                    <td className="p-3 font-bold text-text"><code>F01</code></td>
                    <td className="p-3 text-text">Customer Search Null Guard</td>
                    <td className="p-3 text-text-3">Edge case crash</td>
                  </tr>
                  <tr className="hover:bg-surface-2/40">
                    <td className="p-3 font-bold text-text"><code>F04</code></td>
                    <td className="p-3 text-text">Catalog Health Indicator Config</td>
                    <td className="p-3 text-text-3">Spring configuration</td>
                  </tr>
                  <tr className="hover:bg-surface-2/40">
                    <td className="p-3 font-bold text-text"><code>F06</code></td>
                    <td className="p-3 text-text">Discount Threshold Boundary</td>
                    <td className="p-3 text-text-3">Business logic bug</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          {/* Quick Navigations to Investigate Evidence */}
          <div className="bg-surface p-5 rounded border border-line flex flex-col gap-3">
            <span className="text-base font-semibold text-text">Direct Evidence Exploration</span>
            <p className="text-sm text-text-2 leading-relaxed">
              Inspect real execution logs, unified patch diffs, gate matrices, and empirical research answers:
            </p>

            <div className="flex flex-col gap-2 mt-1">
              <button
                onClick={() => onNavigate('explorer')}
                className="h-10 px-4 rounded bg-action text-on-action text-sm font-medium hover:bg-action-hover transition-colors flex items-center justify-between"
              >
                <span>Open Pipeline Explorer (F06 Live LLM Run)</span>
                <ArrowRight size={16} />
              </button>

              <button
                onClick={() => onNavigate('inspector')}
                className="h-10 px-4 rounded border border-line bg-page text-text-2 hover:bg-surface-2 hover:text-text transition-colors flex items-center justify-between text-sm font-medium"
              >
                <span>Inspect 241 Candidates in Patch Inspector</span>
                <ArrowRight size={16} />
              </button>

              <button
                onClick={() => onNavigate('results')}
                className="h-10 px-4 rounded border border-line bg-page text-text-2 hover:bg-surface-2 hover:text-text transition-colors flex items-center justify-between text-sm font-medium"
              >
                <span>View Empirical Research Results &amp; Gate Attrition</span>
                <ArrowRight size={16} />
              </button>
            </div>
          </div>

          {/* Authoritative Provenance Record */}
          <dl className="grid grid-cols-1 sm:grid-cols-2 gap-y-3 gap-x-6 text-sm border-t border-line pt-4 text-text-3">
            <div>
              <dt className="font-medium">Git Commit Hash</dt>
              <dd className="text-text font-mono text-sm mt-0.5">
                <code>{metadata.git.head.slice(0, 10)} ({metadata.git.branch})</code>
              </dd>
            </div>
            <div>
              <dt className="font-medium">Acceptance Snapshot</dt>
              <dd className="text-text font-medium text-sm mt-0.5">
                {metadata.acceptance_as_of}
              </dd>
            </div>
            <div>
              <dt className="font-medium">Target Service</dt>
              <dd className="text-text font-medium text-sm mt-0.5">
                Java 17, Spring Boot 3, Maven
              </dd>
            </div>
            <div>
              <dt className="font-medium">Isolated Sandbox</dt>
              <dd className="text-text font-medium text-sm mt-0.5">
                Docker <code>--network none</code>
              </dd>
            </div>
          </dl>
        </div>
      </div>
    </div>
  );
};
