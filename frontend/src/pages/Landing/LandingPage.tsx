import React from 'react';
import { EvidenceSnapshot } from '../../types/evidence';
import {
  ArrowRight,
  Shield,
  Cpu,
  Terminal,
  AlertTriangle,
  CheckCircle2,
  ExternalLink,
  ChevronRight,
  Activity,
} from 'lucide-react';

interface LandingPageProps {
  snapshot: EvidenceSnapshot;
  onEnterConsole: (initialTab?: 'overview' | 'explorer' | 'inspector' | 'results') => void;
}

export const LandingPage: React.FC<LandingPageProps> = ({
  snapshot,
  onEnterConsole,
}) => {
  const metadata = snapshot.metadata;
  const isAnalyseStale = metadata?.analyse_check?.status === 'STALE';

  // Smooth scroll helper for on-page anchors
  const scrollToSection = (e: React.MouseEvent<HTMLAnchorElement>, id: string) => {
    e.preventDefault();
    const elem = document.getElementById(id);
    if (elem) {
      elem.scrollIntoView({ behavior: 'smooth' });
    }
  };

  return (
    <div className="min-h-[100dvh] bg-page text-text font-sans flex flex-col selection:bg-lead-tint selection:text-text">
      {/* ─── SITE HEADER ─────────────────────────────────────────────── */}
      <header className="sticky top-0 z-40 h-14 bg-page/95 backdrop-blur-sm border-b border-line px-6 flex items-center justify-between text-sm select-none">
        <div className="flex items-center gap-6">
          <div className="flex items-center gap-3">
            <span className="font-bold text-text text-base tracking-tight">AutoImmune</span>
            <span className="text-text-3 hidden sm:inline text-sm font-medium border-l border-line pl-3">
              Research Prototype
            </span>
          </div>

          <nav className="hidden lg:flex items-center gap-6 text-sm" aria-label="Landing Navigation">
            <a
              href="#how-it-works"
              onClick={(e) => scrollToSection(e, 'how-it-works')}
              className="text-text-2 hover:text-text transition-colors"
            >
              How It Works
            </a>
            <a
              href="#research-problem"
              onClick={(e) => scrollToSection(e, 'research-problem')}
              className="text-text-2 hover:text-text transition-colors"
            >
              Research Problem
            </a>
            <a
              href="#evaluation"
              onClick={(e) => scrollToSection(e, 'evaluation')}
              className="text-text-2 hover:text-text transition-colors"
            >
              Evaluation &amp; RQ
            </a>
            <a
              href="#team"
              onClick={(e) => scrollToSection(e, 'team')}
              className="text-text-2 hover:text-text transition-colors"
            >
              Project Team
            </a>
          </nav>
        </div>

        <div className="flex items-center gap-4">
          <button
            onClick={() => onEnterConsole('overview')}
            className="h-9 px-4 rounded bg-action text-on-action text-sm font-medium hover:bg-action-hover transition-colors flex items-center gap-2"
          >
            <span>Explore Research Console</span>
            <ArrowRight size={15} aria-hidden="true" />
          </button>
        </div>
      </header>

      <main className="flex-1 flex flex-col">
        {/* ─── SECTION 1: INTRODUCTION (HERO) ───────────────────────────── */}
        <section className="px-6 lg:px-12 pt-14 pb-16 max-w-7xl mx-auto w-full border-b border-line">
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-12 items-start">
            {/* Left 7 cols: Academic Context, Registered Title, Problem Statement, CTA */}
            <div className="lg:col-span-7 flex flex-col gap-6">
              <div className="flex flex-col gap-2">
                <span className="text-sm font-semibold text-lead-ink">
                  Final-Year Engineering &amp; Empirical Research Project
                </span>
                <h1 className="text-[32px] sm:text-[38px] lg:text-[42px] font-bold text-text tracking-tight leading-[1.15]">
                  AutoImmune: An Empirical Study of Validation-Gated Deployment Strategies for LLM-Generated Software Patches
                </h1>
              </div>

              <p className="text-base sm:text-lg text-text-2 leading-relaxed">
                AutoImmune investigates how execution-based validation can guide deployment decisions for AI-generated software repairs. It combines AI-assisted diagnosis and patch generation with deterministic validation, risk-based decisions and monitored recovery.
              </p>

              {/* Real provenance summary strip */}
              <dl className="grid grid-cols-2 sm:grid-cols-4 gap-4 py-4 border-y border-line text-sm">
                <div>
                  <dt className="text-text-3 font-medium">Evaluated Units</dt>
                  <dd className="text-text font-bold text-lg mt-0.5 tabular-nums">100 units</dd>
                </div>
                <div>
                  <dt className="text-text-3 font-medium">Recorded Runs</dt>
                  <dd className="text-text font-bold text-lg mt-0.5 tabular-nums">75 executions</dd>
                </div>
                <div>
                  <dt className="text-text-3 font-medium">Docker Sandbox</dt>
                  <dd className="text-text font-bold text-lg mt-0.5"><code>--network none</code></dd>
                </div>
                <div>
                  <dt className="text-text-3 font-medium">Target Stack</dt>
                  <dd className="text-text font-bold text-lg mt-0.5">Java 17 Spring Boot</dd>
                </div>
              </dl>

              {/* Primary Actions */}
              <div className="flex flex-wrap items-center gap-4 pt-2">
                <button
                  onClick={() => onEnterConsole('overview')}
                  className="h-11 px-5 rounded bg-action text-on-action text-base font-semibold hover:bg-action-hover transition-colors flex items-center gap-2.5 shadow-sm"
                >
                  <span>Explore Research Console</span>
                  <ArrowRight size={18} aria-hidden="true" />
                </button>

                <a
                  href="#how-it-works"
                  onClick={(e) => scrollToSection(e, 'how-it-works')}
                  className="h-11 px-5 rounded border border-line bg-surface text-text hover:bg-surface-2 transition-colors flex items-center gap-2 text-base font-medium"
                >
                  <span>How AutoImmune Works</span>
                  <ChevronRight size={16} aria-hidden="true" />
                </a>
              </div>
            </div>

            {/* Right 5 cols: Live Product Preview Snapshot (Authoritative Console Interface) */}
            <div className="lg:col-span-5 flex flex-col gap-4">
              <div className="border border-line rounded-lg bg-surface p-5 shadow-sm flex flex-col gap-4">
                <div className="flex items-center justify-between pb-3 border-b border-line">
                  <div className="flex items-center gap-2">
                    <Activity size={16} className="text-lead-ink" aria-hidden="true" />
                    <span className="font-semibold text-text text-sm">Empirical Evidence Console</span>
                  </div>
                  <span className="text-sm px-2.5 py-0.5 rounded bg-surface-2 text-text-2 border border-line">
                    Verified Snapshot
                  </span>
                </div>

                <div className="flex flex-col gap-3 text-sm">
                  <div className="bg-page p-3.5 rounded border border-line flex flex-col gap-1.5">
                    <div className="flex items-center justify-between text-sm text-text-3">
                      <span>Featured Live LLM Execution</span>
                      <code className="text-sm">F06 Discount Threshold</code>
                    </div>
                    <code className="text-sm text-text font-semibold truncate">
                      f06-live-live-20261108t193456z
                    </code>
                    <div className="flex items-center gap-2 mt-1">
                      <span className="inline-flex items-center gap-1 text-sm px-2 py-0.5 rounded bg-success-tint text-success-ink font-semibold">
                        <CheckCircle2 size={13} /> Auto-Applied &amp; Promoted
                      </span>
                      <span className="text-sm text-text-3">30s canary window clean</span>
                    </div>
                  </div>

                  {/* Sequential Attrition Snapshot */}
                  <div className="flex flex-col gap-2 pt-1">
                    <span className="text-sm font-semibold text-text-3">
                      Validation Gate Attrition (100 Deduplicated Units)
                    </span>
                    <div className="space-y-1.5 text-sm">
                      <div className="flex items-center justify-between">
                        <span className="text-text">V0 Syntax &amp; Compilation</span>
                        <span className="text-danger-ink font-semibold tabular-nums">31 stopped (31.0%)</span>
                      </div>
                      <div className="w-full bg-surface-2 h-2 rounded overflow-hidden">
                        <div className="bg-danger-ink h-full rounded" style={{ width: '31%' }} />
                      </div>

                      <div className="flex items-center justify-between pt-1">
                        <span className="text-text">V1 Target Reproduction Test</span>
                        <span className="text-danger-ink font-semibold tabular-nums">24 stopped (24.0%)</span>
                      </div>
                      <div className="w-full bg-surface-2 h-2 rounded overflow-hidden">
                        <div className="bg-danger-ink h-full rounded" style={{ width: '24%' }} />
                      </div>

                      <div className="flex items-center justify-between pt-1">
                        <span className="text-text">V2 Regression Test Suite</span>
                        <span className="text-danger-ink font-semibold tabular-nums">9 stopped (9.0%)</span>
                      </div>
                      <div className="w-full bg-surface-2 h-2 rounded overflow-hidden">
                        <div className="bg-danger-ink h-full rounded" style={{ width: '9%' }} />
                      </div>

                      <div className="flex items-center justify-between pt-1">
                        <span className="text-text">V3 Differential Semgrep Security</span>
                        <span className="text-danger-ink font-semibold tabular-nums">8 stopped (8.0%)</span>
                      </div>
                      <div className="w-full bg-surface-2 h-2 rounded overflow-hidden">
                        <div className="bg-danger-ink h-full rounded" style={{ width: '8%' }} />
                      </div>
                    </div>
                  </div>

                  <button
                    onClick={() => onEnterConsole('explorer')}
                    className="w-full mt-2 h-9 px-3 rounded border border-line bg-page hover:bg-surface-2 text-text text-sm font-medium transition-colors flex items-center justify-center gap-1.5"
                  >
                    <span>Inspect Full 10-Stage Pipeline</span>
                    <ExternalLink size={14} aria-hidden="true" />
                  </button>
                </div>
              </div>

              {isAnalyseStale && (
                <div className="p-3 bg-warning-tint/30 border border-warning-line/50 rounded flex items-start gap-2.5 text-sm text-text-2">
                  <Terminal size={14} className="text-warning-ink flex-shrink-0 mt-0.5" aria-hidden="true" />
                  <span>
                    <strong>Authoritative Provenance:</strong> Derived CSV summaries are preserved honestly as STALE relative to raw run additions per research protocol.
                  </span>
                </div>
              )}
            </div>
          </div>
        </section>

        {/* ─── SECTION 2: HOW AUTOIMMUNE WORKS (PIPELINE ARCHITECTURE) ─── */}
        <section id="how-it-works" className="px-6 lg:px-12 py-16 max-w-7xl mx-auto w-full border-b border-line">
          <div className="flex flex-col gap-3 mb-10">
            <span className="text-sm font-semibold text-lead-ink">
              System Architecture
            </span>
            <h2 className="text-[28px] sm:text-[32px] font-bold text-text tracking-tight">
              How AutoImmune Works: Hybrid AI/Deterministic Pipeline
            </h2>
            <p className="text-base text-text-2 max-w-3xl leading-relaxed">
              AutoImmune enforces a strict architectural boundary: an LLM is used <strong>ONLY</strong> for root-cause diagnosis and candidate patch drafting. All execution gates, safety tiering, deployment orchestration, and canary rollbacks are executed by deterministic code.
            </p>
          </div>

          {/* AI vs Deterministic Boundary Callout Banner */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-10">
            <div className="p-5 rounded border border-lead-line/40 bg-lead-tint/30 flex flex-col gap-2">
              <div className="flex items-center gap-2 text-lead-ink font-semibold text-base">
                <Cpu size={18} aria-hidden="true" />
                <span>AI Responsibility (Probabilistic)</span>
              </div>
              <p className="text-sm text-text-2 leading-relaxed">
                Invoked strictly twice per incident: first to rank suspect files based on error logs (<code className="text-sm">diagnose()</code>), then to generate up to 3 candidate unified diffs (<code className="text-sm">draft_patches()</code>). No autonomous loops or tool-calling allowed.
              </p>
            </div>

            <div className="p-5 rounded border border-line bg-surface flex flex-col gap-2">
              <div className="flex items-center gap-2 text-text font-semibold text-base">
                <Shield size={18} className="text-success-ink" aria-hidden="true" />
                <span>Deterministic Control (Rule-Gated)</span>
              </div>
              <p className="text-sm text-text-2 leading-relaxed">
                Isolated Docker container execution, 4 sequential validation gates, rule-based tiering (<code className="text-sm">config/decision.yaml</code>), image swapping, Actuator health canary window, and automated sub-second rollback.
              </p>
            </div>
          </div>

          {/* 9-Stage Pipeline Visualization */}
          <div className="border border-line rounded-lg overflow-hidden bg-surface">
            <div className="p-4 bg-surface-2 border-b border-line flex items-center justify-between text-sm">
              <span className="font-semibold text-text">Sequential 9-Stage Execution Lifecycle</span>
              <span className="text-text-3">Full evidence captured per stage</span>
            </div>

            <div className="divide-y divide-line">
              {/* Stage 1 */}
              <div className="p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-2 hover:bg-page transition-colors text-sm">
                <div className="flex items-start sm:items-center gap-3">
                  <span className="w-6 h-6 rounded-full bg-surface-2 border border-line flex items-center justify-center font-bold text-sm text-text-2 flex-shrink-0">
                    1
                  </span>
                  <div>
                    <span className="font-semibold text-text block sm:inline">Fault Detection</span>
                    <span className="text-text-3 sm:ml-2">Automated probe detects service anomaly or error breach</span>
                  </div>
                </div>
                <span className="text-sm px-2.5 py-0.5 rounded bg-surface-2 text-text-2 font-medium self-start sm:self-auto">
                  Deterministic
                </span>
              </div>

              {/* Stage 2 */}
              <div className="p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-2 hover:bg-page transition-colors text-sm bg-lead-tint/10">
                <div className="flex items-start sm:items-center gap-3">
                  <span className="w-6 h-6 rounded-full bg-lead-tint border border-lead-line flex items-center justify-center font-bold text-sm text-lead-ink flex-shrink-0">
                    2
                  </span>
                  <div>
                    <span className="font-semibold text-text block sm:inline">Root-Cause Diagnosis</span>
                    <span className="text-text-2 sm:ml-2">LLM samples fault localization hypotheses from error logs</span>
                  </div>
                </div>
                <span className="text-sm px-2.5 py-0.5 rounded bg-lead-tint text-lead-ink font-semibold self-start sm:self-auto">
                  AI Model
                </span>
              </div>

              {/* Stage 3 */}
              <div className="p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-2 hover:bg-page transition-colors text-sm bg-lead-tint/10">
                <div className="flex items-start sm:items-center gap-3">
                  <span className="w-6 h-6 rounded-full bg-lead-tint border border-lead-line flex items-center justify-center font-bold text-sm text-lead-ink flex-shrink-0">
                    3
                  </span>
                  <div>
                    <span className="font-semibold text-text block sm:inline">Candidate Generation</span>
                    <span className="text-text-2 sm:ml-2">LLM drafts up to 3 candidate unified diffs for the diagnosed file</span>
                  </div>
                </div>
                <span className="text-sm px-2.5 py-0.5 rounded bg-lead-tint text-lead-ink font-semibold self-start sm:self-auto">
                  AI Model
                </span>
              </div>

              {/* Stage 4: Docker Gates (Expanded) */}
              <div className="p-5 bg-page border-y border-line">
                <div className="flex items-center justify-between mb-3 text-sm">
                  <div className="flex items-center gap-3">
                    <span className="w-6 h-6 rounded-full bg-lead text-on-lead flex items-center justify-center font-bold text-sm flex-shrink-0">
                      4
                    </span>
                    <span className="font-bold text-text text-base">Docker Sandbox Validation Gates (V0–V3)</span>
                  </div>
                  <span className="text-sm px-2.5 py-0.5 rounded bg-surface-2 text-text-2 font-medium">
                    Deterministic · <code>--network none</code>
                  </span>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 mt-3 text-sm">
                  <div className="p-3.5 rounded border border-line bg-surface flex flex-col gap-1">
                    <div className="flex items-center justify-between">
                      <code className="font-bold text-text text-sm">V0</code>
                      <span className="text-sm text-text-3">Compilation</span>
                    </div>
                    <span className="font-semibold text-text text-sm mt-0.5">Syntax &amp; Maven Build</span>
                    <p className="text-text-3 text-sm leading-relaxed mt-1">
                      Verifies clean <code className="text-sm">git apply --check</code> and isolated <code className="text-sm">mvn compile</code> without syntax or type errors.
                    </p>
                  </div>

                  <div className="p-3.5 rounded border border-line bg-surface flex flex-col gap-1">
                    <div className="flex items-center justify-between">
                      <code className="font-bold text-text text-sm">V1</code>
                      <span className="text-sm text-text-3">Reproduction</span>
                    </div>
                    <span className="font-semibold text-text text-sm mt-0.5">Target Visible Test</span>
                    <p className="text-text-3 text-sm leading-relaxed mt-1">
                      Executes reproduction unit test to verify the patch actually resolves the observed incident.
                    </p>
                  </div>

                  <div className="p-3.5 rounded border border-line bg-surface flex flex-col gap-1">
                    <div className="flex items-center justify-between">
                      <code className="font-bold text-text text-sm">V2</code>
                      <span className="text-sm text-text-3">Regression</span>
                    </div>
                    <span className="font-semibold text-text text-sm mt-0.5">Regression Test Suite</span>
                    <p className="text-text-3 text-sm leading-relaxed mt-1">
                      Runs the full existing test suite to ensure the repair does not break healthy endpoints.
                    </p>
                  </div>

                  <div className="p-3.5 rounded border border-line bg-surface flex flex-col gap-1">
                    <div className="flex items-center justify-between">
                      <code className="font-bold text-text text-sm">V3</code>
                      <span className="text-sm text-text-3">Security</span>
                    </div>
                    <span className="font-semibold text-text text-sm mt-0.5">Semgrep Differential</span>
                    <p className="text-text-3 text-sm leading-relaxed mt-1">
                      Performs differential static security analysis. Only <strong>NEW</strong> vulnerabilities trigger rejection.
                    </p>
                  </div>
                </div>
              </div>

              {/* Stage 5 */}
              <div className="p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-2 hover:bg-page transition-colors text-sm">
                <div className="flex items-start sm:items-center gap-3">
                  <span className="w-6 h-6 rounded-full bg-surface-2 border border-line flex items-center justify-center font-bold text-sm text-text-2 flex-shrink-0">
                    5
                  </span>
                  <div>
                    <span className="font-semibold text-text block sm:inline">Deterministic Risk Decisions</span>
                    <span className="text-text-3 sm:ml-2">Threshold rules evaluate diff boundaries, file drift and gate passes</span>
                  </div>
                </div>
                <span className="text-sm px-2.5 py-0.5 rounded bg-surface-2 text-text-2 font-medium self-start sm:self-auto">
                  AUTO_APPLY / ESCALATE / REJECT
                </span>
              </div>

              {/* Stage 6 */}
              <div className="p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-2 hover:bg-page transition-colors text-sm">
                <div className="flex items-start sm:items-center gap-3">
                  <span className="w-6 h-6 rounded-full bg-surface-2 border border-line flex items-center justify-center font-bold text-sm text-text-2 flex-shrink-0">
                    6
                  </span>
                  <div>
                    <span className="font-semibold text-text block sm:inline">Human Approval Gate</span>
                    <span className="text-text-3 sm:ml-2">Escalated medium-risk repairs require explicit human engineer sign-off</span>
                  </div>
                </div>
                <span className="text-sm px-2.5 py-0.5 rounded bg-surface-2 text-text-2 font-medium self-start sm:self-auto">
                  CLI / Tool Relayed
                </span>
              </div>

              {/* Stage 7 */}
              <div className="p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-2 hover:bg-page transition-colors text-sm">
                <div className="flex items-start sm:items-center gap-3">
                  <span className="w-6 h-6 rounded-full bg-surface-2 border border-line flex items-center justify-center font-bold text-sm text-text-2 flex-shrink-0">
                    7
                  </span>
                  <div>
                    <span className="font-semibold text-text block sm:inline">Canary Deployment &amp; Health Window</span>
                    <span className="text-text-3 sm:ml-2">Patched image deployed; 30s health window verifies /actuator/health &amp; latency</span>
                  </div>
                </div>
                <span className="text-sm px-2.5 py-0.5 rounded bg-surface-2 text-text-2 font-medium self-start sm:self-auto">
                  Sub-second Container Cutover
                </span>
              </div>

              {/* Stage 8 */}
              <div className="p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-2 hover:bg-page transition-colors text-sm">
                <div className="flex items-start sm:items-center gap-3">
                  <span className="w-6 h-6 rounded-full bg-surface-2 border border-line flex items-center justify-center font-bold text-sm text-text-2 flex-shrink-0">
                    8
                  </span>
                  <div>
                    <span className="font-semibold text-text block sm:inline">Promotion or Rollback</span>
                    <span className="text-text-3 sm:ml-2">Breach triggers immediate rollback swap to preserved prior image</span>
                  </div>
                </div>
                <span className="text-sm px-2.5 py-0.5 rounded bg-surface-2 text-text-2 font-medium self-start sm:self-auto">
                  Automated Container Swap
                </span>
              </div>

              {/* Stage 9 */}
              <div className="p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-2 hover:bg-page transition-colors text-sm">
                <div className="flex items-start sm:items-center gap-3">
                  <span className="w-6 h-6 rounded-full bg-surface-2 border border-line flex items-center justify-center font-bold text-sm text-text-2 flex-shrink-0">
                    9
                  </span>
                  <div>
                    <span className="font-semibold text-text block sm:inline">Evidence Recording</span>
                    <span className="text-text-3 sm:ml-2">Audit artifacts written to runs/ and appended to authoritative evidence.jsonl</span>
                  </div>
                </div>
                <span className="text-sm px-2.5 py-0.5 rounded bg-surface-2 text-text-2 font-medium self-start sm:self-auto">
                  JSON Lines Ledger
                </span>
              </div>
            </div>
          </div>
        </section>

        {/* ─── SECTION 3: THE RESEARCH PROBLEM ─────────────────────────── */}
        <section id="research-problem" className="px-6 lg:px-12 py-16 max-w-7xl mx-auto w-full border-b border-line">
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-12 items-start">
            <div className="lg:col-span-6 flex flex-col gap-5">
              <span className="text-sm font-semibold text-lead-ink">
                The Research Problem
              </span>
              <h2 className="text-[28px] sm:text-[32px] font-bold text-text tracking-tight leading-snug">
                Passing Validation Gates Does Not Guarantee Semantic Correctness
              </h2>

              <p className="text-base text-text-2 leading-relaxed">
                A central challenge in automated program repair is the <strong>overfitting hazard</strong>: large language models frequently generate patches that pass all visible unit and integration tests by special-casing inputs, hardcoding outputs, or altering boundary invariants.
              </p>

              <p className="text-base text-text-2 leading-relaxed">
                Treating every test-passing repair as deployment-safe leads to <em>silent escapes</em> in production. AutoImmune investigates how deep validation evidence must be, what each sequential gate catches, and whether deterministic risk tiering can identify unsafe patches without relying on human review for every fix.
              </p>

              <div className="p-4 rounded border border-line bg-surface flex flex-col gap-1 text-sm text-text-2">
                <span className="font-semibold text-text">The Core Research Hypothesis:</span>
                <p>
                  Execution-based validation depth combined with diff scope bounding can safely automate a subset of low-risk repairs while maintaining high rejection precision on regressions and vulnerabilities.
                </p>
              </div>
            </div>

            {/* Documented Case Study from Real Snapshot */}
            <div className="lg:col-span-6 flex flex-col gap-4">
              <div className="p-6 rounded-lg border border-line bg-surface flex flex-col gap-4">
                <div className="flex items-center justify-between pb-3 border-b border-line">
                  <div className="flex items-center gap-2">
                    <AlertTriangle size={16} className="text-warning-ink" aria-hidden="true" />
                    <span className="font-semibold text-text text-sm">Empirical Case Study: Silent Semantic Escape</span>
                  </div>
                  <span className="text-sm px-2.5 py-0.5 rounded bg-warning-tint text-warning-ink font-semibold">
                    Policy B3 Escape
                  </span>
                </div>

                <div className="flex flex-col gap-2 text-sm">
                  <div className="flex items-center justify-between text-sm text-text-3">
                    <span>Incident: Fault F01 Customer Search Null Guard</span>
                    <code>F01-scripted-fb8fb0d5</code>
                  </div>
                  <h3 className="text-base font-bold text-text">
                    Whitespace-Only Query Invariant Bypass
                  </h3>
                  <p className="text-text-2 leading-relaxed text-sm">
                    The patch guarded against null strings but failed to validate whitespace-only input strings. Because existing visible test suites checked null queries but omitted whitespace assertions, the patch passed V0, V1, V2, and Semgrep V3 cleanly.
                  </p>
                </div>

                {/* Evidence Table */}
                <dl className="grid grid-cols-2 gap-3 p-3.5 bg-page rounded border border-line text-sm">
                  <div>
                    <dt className="text-text-3 text-sm font-medium">Runtime Decision</dt>
                    <dd className="font-semibold text-success-ink text-sm mt-0.5">AUTO_APPLY (Promoted)</dd>
                  </div>
                  <div>
                    <dt className="text-text-3 text-sm font-medium">Docker Gates V0–V3</dt>
                    <dd className="font-semibold text-text text-sm mt-0.5">4 of 4 Passed</dd>
                  </div>
                  <div>
                    <dt className="text-text-3 text-sm font-medium">Canary Health Window</dt>
                    <dd className="font-semibold text-text text-sm mt-0.5">UP (HTTP 200, 31ms)</dd>
                  </div>
                  <div>
                    <dt className="text-text-3 text-sm font-medium">Independent Offline Oracle</dt>
                    <dd className="font-semibold text-danger-ink text-sm mt-0.5">Overfitting (Unsafe)</dd>
                  </div>
                </dl>

                <p className="text-sm text-text-3 leading-relaxed">
                  * Ground-truth evaluation was verified post-hoc by independent hidden oracle test suites (<code>tools/oracle.py</code>) never exposed to the runtime pipeline.
                </p>
              </div>
            </div>
          </div>
        </section>

        {/* ─── SECTION 4: RESEARCH OBJECTIVES & EVALUATION ─────────────── */}
        <section id="evaluation" className="px-6 lg:px-12 py-16 max-w-7xl mx-auto w-full border-b border-line">
          <div className="flex flex-col gap-3 mb-10">
            <span className="text-sm font-semibold text-lead-ink">
              Research Objectives
            </span>
            <h2 className="text-[28px] sm:text-[32px] font-bold text-text tracking-tight">
              Evaluation &amp; The Three Research Questions
            </h2>
            <p className="text-base text-text-2 max-w-3xl leading-relaxed">
              AutoImmune evaluates repair viability across four formal deployment policies (B0–B3) to measure how validation depth impacts human review burden and unsafe patch escapes.
            </p>
          </div>

          {/* Three Research Questions Grid */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-12">
            <div className="p-6 rounded-lg border border-line bg-surface flex flex-col gap-3">
              <span className="text-sm font-bold text-lead-ink">Research Question 1</span>
              <h3 className="text-lg font-bold text-text leading-snug">
                Gate Catch Effectiveness
              </h3>
              <p className="text-sm text-text-2 leading-relaxed">
                What classes of defects are caught by successive validation gates (syntax, reproduction, regression, static security), and what execution time does each gate introduce?
              </p>
              <div className="mt-auto pt-3 border-t border-line text-sm text-text-3">
                Key finding: Layered filtering catches syntax errors early (V0 median 5.8s) before expensive integration suites.
              </div>
            </div>

            <div className="p-6 rounded-lg border border-line bg-surface flex flex-col gap-3">
              <span className="text-sm font-bold text-lead-ink">Research Question 2</span>
              <h3 className="text-lg font-bold text-text leading-snug">
                Unattended Deployment Safety
              </h3>
              <p className="text-sm text-text-2 leading-relaxed">
                How effectively can recorded execution evidence and canary health windows identify unsafe repairs before production damage occurs?
              </p>
              <div className="mt-auto pt-3 border-t border-line text-sm text-text-3">
                Key finding: 100% of tested regressive and insecure challenge repairs were blocked before promotion.
              </div>
            </div>

            <div className="p-6 rounded-lg border border-line bg-surface flex flex-col gap-3">
              <span className="text-sm font-bold text-lead-ink">Research Question 3</span>
              <h3 className="text-lg font-bold text-text leading-snug">
                Human Review Trade-off
              </h3>
              <p className="text-sm text-text-2 leading-relaxed">
                Under what conditions can validation evidence support autonomous auto-application, reducing human review burden without compromising safety?
              </p>
              <div className="mt-auto pt-3 border-t border-line text-sm text-text-3">
                Key finding: B3 policy permits autonomous promotion for tightly bounded diffs while escalating complex repairs.
              </div>
            </div>
          </div>

          {/* Policy Comparison Table (B0 - B3) */}
          <div className="border border-line rounded-lg overflow-hidden bg-surface mb-8">
            <div className="p-4 bg-surface-2 border-b border-line flex items-center justify-between text-sm">
              <span className="font-semibold text-text">Policy Gating Strategy Comparison (B0–B3)</span>
              <span className="text-text-3 text-sm">Evaluated across 100 deduplicated research units</span>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full min-w-[640px] text-left text-sm border-collapse">
                <thead className="bg-surface-2 text-text-3 border-b border-line text-sm">
                  <tr>
                    <th className="p-3 font-medium">Policy</th>
                    <th className="p-3 font-medium">Deployment Rule</th>
                    <th className="p-3 font-medium">Human Review Rate (HIR)</th>
                    <th className="p-3 font-medium">Unsafe Escape Rate</th>
                    <th className="p-3 font-medium">Characteristics</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line text-sm">
                  <tr className="hover:bg-page transition-colors">
                    <td className="p-3 font-bold text-text"><code>B0</code></td>
                    <td className="p-3 text-text">Human reviews everything</td>
                    <td className="p-3 font-semibold text-danger-ink tabular-nums">100.0% (all escalated)</td>
                    <td className="p-3 font-semibold text-success-ink tabular-nums">0.0% (idealized)</td>
                    <td className="p-3 text-text-3">Maximal human overhead; complete pipeline stall on every fix</td>
                  </tr>
                  <tr className="hover:bg-page transition-colors">
                    <td className="p-3 font-bold text-text"><code>B1</code></td>
                    <td className="p-3 text-text">Auto-apply if V0 + V1 pass</td>
                    <td className="p-3 font-semibold text-text tabular-nums">0.0%</td>
                    <td className="p-3 font-semibold text-danger-ink tabular-nums">76.3% (scripted)</td>
                    <td className="p-3 text-text-3">Naive testing; permits severe regressions and security breaches</td>
                  </tr>
                  <tr className="hover:bg-page transition-colors">
                    <td className="p-3 font-bold text-text"><code>B2</code></td>
                    <td className="p-3 text-text">Auto-apply if V0 – V2 pass</td>
                    <td className="p-3 font-semibold text-text tabular-nums">0.0%</td>
                    <td className="p-3 font-semibold text-warning-ink tabular-nums">52.6% (scripted)</td>
                    <td className="p-3 text-text-3">Catches regressions, but vulnerable to differential security flaws</td>
                  </tr>
                  <tr className="hover:bg-page transition-colors bg-lead-tint/15">
                    <td className="p-3 font-bold text-lead-ink"><code>B3</code></td>
                    <td className="p-3 font-semibold text-text">AutoImmune Full Gated Defense</td>
                    <td className="p-3 font-semibold text-lead-ink tabular-nums">6.4% scripted · 3.8% LLM</td>
                    <td className="p-3 font-semibold text-text tabular-nums">28.9% scripted · 28.6% LLM</td>
                    <td className="p-3 text-text-2">V0–V3 + diff bounds + multi-file drift guard + canary window</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <div className="flex justify-start">
            <button
              onClick={() => onEnterConsole('results')}
              className="h-10 px-4 rounded border border-line bg-surface hover:bg-surface-2 text-text text-sm font-medium transition-colors flex items-center gap-2"
            >
              <span>View Detailed Statistical Results &amp; Charts</span>
              <ArrowRight size={15} aria-hidden="true" />
            </button>
          </div>
        </section>

        {/* ─── SECTION 5: PROJECT TEAM & ACADEMIC INFORMATION ──────────── */}
        <section id="team" className="px-6 lg:px-12 py-16 max-w-7xl mx-auto w-full">
          <div className="flex flex-col gap-3 mb-10">
            <span className="text-sm font-semibold text-lead-ink">
              Academic Identity
            </span>
            <h2 className="text-[28px] sm:text-[32px] font-bold text-text tracking-tight">
              Project Team
            </h2>
            <p className="text-base text-text-2 max-w-3xl leading-relaxed">
              Final-year engineering research project conducted under the Department of Computer Science &amp; Engineering.
            </p>
          </div>

          {/* Equal Visual Importance Team Grid (3 members, strictly academic presentation) */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-12">
            {/* Member 1: Agni MN */}
            <div className="p-6 rounded-lg border border-line bg-surface flex flex-col gap-2">
              <span className="text-sm font-semibold text-text-3">
                Researcher &amp; Candidate Engineer
              </span>
              <h3 className="text-xl font-bold text-text mt-1">
                Agni MN
              </h3>
              <div className="flex items-center gap-2 mt-1">
                <span className="text-sm text-text-3 font-medium">USN:</span>
                <code className="text-sm font-semibold text-text bg-page px-2 py-0.5 rounded border border-line">
                  23ETIS411005
                </code>
              </div>
            </div>

            {/* Member 2: Pradeep S */}
            <div className="p-6 rounded-lg border border-line bg-surface flex flex-col gap-2">
              <span className="text-sm font-semibold text-text-3">
                Researcher &amp; Candidate Engineer
              </span>
              <h3 className="text-xl font-bold text-text mt-1">
                Pradeep S
              </h3>
              <div className="flex items-center gap-2 mt-1">
                <span className="text-sm text-text-3 font-medium">USN:</span>
                <code className="text-sm font-semibold text-text bg-page px-2 py-0.5 rounded border border-line">
                  23ETIS411035
                </code>
              </div>
            </div>

            {/* Member 3: Nehal S */}
            <div className="p-6 rounded-lg border border-line bg-surface flex flex-col gap-2">
              <span className="text-sm font-semibold text-text-3">
                Researcher &amp; Candidate Engineer
              </span>
              <h3 className="text-xl font-bold text-text mt-1">
                Nehal S
              </h3>
              <div className="flex items-center gap-2 mt-1">
                <span className="text-sm text-text-3 font-medium">USN:</span>
                <code className="text-sm font-semibold text-text bg-page px-2 py-0.5 rounded border border-line">
                  23ETIS411046
                </code>
              </div>
            </div>
          </div>

          {/* Technical Implementation Stack Details */}
          <div className="border border-line rounded-lg p-6 bg-surface flex flex-col gap-4">
            <h3 className="text-base font-bold text-text">
              Underlying System &amp; Research Stack
            </h3>

            <dl className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6 text-sm">
              <div>
                <dt className="text-text-3 font-medium">Orchestrator Pipeline</dt>
                <dd className="text-text font-semibold mt-1">Python 3.12 (CLI &amp; Runners)</dd>
                <p className="text-text-3 text-sm mt-1">Deterministic state machines, zero agent loops</p>
              </div>

              <div>
                <dt className="text-text-3 font-medium">Target Microservice</dt>
                <dd className="text-text font-semibold mt-1">Java 17, Spring Boot 3</dd>
                <p className="text-text-3 text-sm mt-1">order-service with Maven test suite</p>
              </div>

              <div>
                <dt className="text-text-3 font-medium">Isolation &amp; Security</dt>
                <dd className="text-text font-semibold mt-1">Docker &amp; Semgrep</dd>
                <p className="text-text-3 text-sm mt-1"><code>--network none</code> sandboxing, differential scans</p>
              </div>

              <div>
                <dt className="text-text-3 font-medium">Research Tooling</dt>
                <dd className="text-text font-semibold mt-1">React, TypeScript, Vite</dd>
                <p className="text-text-3 text-sm mt-1">Oxfords research interface design</p>
              </div>
            </dl>

            <div className="pt-4 border-t border-line flex flex-col sm:flex-row sm:items-center justify-between gap-4">
              <span className="text-sm text-text-3">
                Full experimental data, candidate diffs and recorded execution logs are available in the Research Console.
              </span>
              <button
                onClick={() => onEnterConsole('overview')}
                className="h-10 px-5 rounded bg-action text-on-action text-sm font-semibold hover:bg-action-hover transition-colors flex items-center gap-2 self-start sm:self-auto flex-shrink-0"
              >
                <span>Enter Research Console</span>
                <ArrowRight size={16} aria-hidden="true" />
              </button>
            </div>
          </div>
        </section>
      </main>

      {/* ─── SITE FOOTER ─────────────────────────────────────────────── */}
      <footer className="border-t border-line bg-surface px-6 lg:px-12 py-8 text-sm text-text-3">
        <div className="max-w-7xl mx-auto flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div className="flex flex-col gap-1">
            <span className="font-semibold text-text text-sm">
              AutoImmune Research Project
            </span>
            <span className="text-sm text-text-3">
              An Empirical Study of Validation-Gated Deployment Strategies for LLM-Generated Software Patches
            </span>
          </div>

          <div className="flex items-center gap-6 text-sm">
            <button
              onClick={() => onEnterConsole('overview')}
              className="text-text-2 hover:text-text transition-colors"
            >
              Console Overview
            </button>
            <button
              onClick={() => onEnterConsole('results')}
              className="text-text-2 hover:text-text transition-colors"
            >
              Research Results
            </button>
            <a
              href="#top"
              onClick={(e) => {
                e.preventDefault();
                window.scrollTo({ top: 0, behavior: 'smooth' });
              }}
              className="text-text-3 hover:text-text transition-colors"
            >
              Back to Top ↑
            </a>
          </div>
        </div>
      </footer>
    </div>
  );
};
