import React from 'react';
import { Cohort, EvidenceSnapshot, GateBenefit, GateTiming, ValidationCostData } from '../../types/evidence';
import { COHORT_LABEL, COHORT_SERIES, COHORT_SHORT, COHORTS, minutes } from '../../components/research/format';
import { CumulativeChart, GroupedBars, Legend } from '../../components/research/charts';
import { ExtensionUnavailable, Provenance } from '../../components/research/Provenance';

/**
 * Validation Cost (RQ3). Displays results/cost/validation_cost.json as exported into the evidence snapshot.
 * Every number, ratio and conclusion is computed by tools/validation_cost.py.
 */
export const ValidationCost: React.FC<{ snapshot: EvidenceSnapshot }> = ({ snapshot }) => {
  const ext = snapshot.validation_cost;
  if (!ext?.available || !ext.data) {
    return (
      <ExtensionUnavailable
        title="Validation Cost"
        reason={ext?.reason ?? 'The snapshot has no validation_cost section. Run python -m tools.validation_cost.'}
      />
    );
  }
  return <CostBody data={ext.data} source={ext.source} sha={ext.sha256_12} />;
};

const H2 = 'text-[20px] font-semibold text-text tracking-tight';
const LEAD = 'text-sm text-text-2 leading-relaxed max-w-[80ch]';
const TH = 'px-3 py-2 font-medium text-text-3 text-left';
const THR = 'px-3 py-2 font-medium text-text-3 text-right';
const TDR = 'px-3 py-2 text-text text-right tabular-nums';
const GATES = ['V0', 'V1', 'V2', 'V3'] as const;
const GATE_NAME: Record<string, string> = {
  V0: 'V0 apply and compile',
  V1: 'V1 target test',
  V2: 'V2 full suite',
  V3: 'V3 Semgrep',
};

const f1 = (x: number | null | undefined) => (x == null ? '–' : x.toFixed(1));

const CostBody: React.FC<{ data: ValidationCostData; source: string; sha?: string }> = ({ data, source, sha }) => {
  const timing = (c: Cohort) => data.cohorts[c].timing;
  const benefit = (c: Cohort) => data.cohorts[c].benefit;

  return (
    <div className="flex-1 flex flex-col bg-page text-text">
      <div className="w-full max-w-[1440px] mx-auto px-8 pt-8 pb-20 flex flex-col gap-12">
        <header className="flex flex-col gap-2">
          <h1 className="text-[28px] font-bold tracking-tight leading-tight">Validation Cost</h1>
          <p className="text-base text-text-2 max-w-[80ch]">
            RQ3: which validation gates stop the most unsafe patches for the execution time they cost?
          </p>
          <Provenance
            source={source}
            sha={sha}
            generator={data.generator}
            timestamp={data.analysis_timestamp}
            methodsDoc={data.methods_doc}
            artifacts={data.source_artifacts}
          />
        </header>

        {/* Answer first */}
        <section aria-labelledby="vc-answer" className="flex flex-col gap-4">
          <h2 id="vc-answer" className={H2}>What the measurements show</h2>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-x-12 gap-y-6 border-y border-line py-6">
            {COHORTS.map((c) => (
              <div key={c} className="flex flex-col gap-2 min-w-0">
                <h3 className="text-sm font-semibold">{COHORT_LABEL[c]}</h3>
                <p className="text-sm text-text-2 tabular-nums">
                  {benefit(c).judged_patches} distinct judged patches, {benefit(c).unsafe_patches} unsafe. Timing from{' '}
                  {timing(c)[0].executions} V0 executions.
                </p>
                <ul className="list-disc pl-5 flex flex-col gap-1 text-sm text-text leading-relaxed">
                  {data.cohorts[c].conclusions.map((s) => (
                    <li key={s}>{s}</li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
          <p className="text-sm text-text-3 max-w-[90ch]">
            Observational, not causal. The gates always ran in the order V0, V1, V2, V3, so a later gate only saw the
            patches every earlier gate passed. {data.definitions.uniqueness.charAt(0).toUpperCase() + data.definitions.uniqueness.slice(1)}.
          </p>
        </section>

        {/* Per-cohort tables */}
        {COHORTS.map((c) => (
          <CohortTable key={c} cohort={c} timing={timing(c)} benefit={benefit(c).gates} unsafe={benefit(c).unsafe_patches} judged={benefit(c).judged_patches} />
        ))}

        {/* Charts */}
        <section aria-labelledby="vc-charts" className="flex flex-col gap-8">
          <h2 id="vc-charts" className={H2}>Cost and benefit compared</h2>
          <Legend items={COHORTS.map((c) => ({ name: COHORT_SHORT[c], color: COHORT_SERIES[c] }))} />

          <div className="grid grid-cols-1 xl:grid-cols-2 gap-10">
            <div className="flex flex-col gap-2 min-w-0">
              <h3 className="text-base font-semibold">Gate duration per execution</h3>
              <p className="text-sm text-text-2">
                Bar: median seconds. Black tick: p95. All eligible executions with a recorded duration.
              </p>
              <GroupedBars
                categories={[...GATES]}
                unit="seconds"
                label="Median and 95th percentile gate duration per execution, per cohort"
                series={COHORTS.map((c) => ({
                  name: COHORT_SHORT[c],
                  color: COHORT_SERIES[c],
                  values: timing(c).map((t) => t.median_s),
                  markers: timing(c).map((t) => t.p95_s),
                  labels: timing(c).map((t) =>
                    t.timed ? `${f1(t.median_s)} s, p95 ${f1(t.p95_s)} s (n=${t.timed})` : 'no timed run',
                  ),
                }))}
              />
            </div>
            <div className="flex flex-col gap-2 min-w-0">
              <h3 className="text-base font-semibold">Unsafe patches stopped first at each gate</h3>
              <p className="text-sm text-text-2">Distinct judged patches. “not run” means no judged patch reached the gate.</p>
              <GroupedBars
                categories={[...GATES]}
                unit="unsafe patches"
                label="Unsafe patches first stopped at each gate, per cohort"
                series={COHORTS.map((c) => ({
                  name: COHORT_SHORT[c],
                  color: COHORT_SERIES[c],
                  values: benefit(c).gates.map((g) => (g.reached ? g.unsafe_stopped : null)),
                  labels: benefit(c).gates.map((g) =>
                    g.reached ? `${g.unsafe_stopped} of ${g.unsafe_reached} unsafe reaching it` : 'not run',
                  ),
                }))}
              />
            </div>
          </div>

          <div className="flex flex-col gap-2 min-w-0">
            <h3 className="text-base font-semibold">Safety versus cost</h3>
            <p className={LEAD}>
              Each point adds the next gate. Horizontal: gate-minutes spent on the judged patches so far. Vertical:
              share of that cohort's unsafe patches stopped so far. A steep segment is a gate that stops many unsafe
              patches for little time.
            </p>
            <CumulativeChart
              xLabel="Cumulative gate-minutes (distinct judged patches)"
              yLabel="Unsafe patches stopped"
              label="Cumulative share of unsafe patches stopped against cumulative gate-minutes, per cohort"
              series={COHORTS.map((c) => ({
                name: COHORT_SHORT[c],
                color: COHORT_SERIES[c],
                points: benefit(c).gates.map((g) => ({
                  x: g.cumulative_seconds / 60,
                  y: benefit(c).unsafe_patches ? g.cumulative_unsafe_stopped / benefit(c).unsafe_patches : 0,
                  label: `${g.gate} ${g.cumulative_unsafe_stopped}/${benefit(c).unsafe_patches}`,
                })),
              }))}
            />
          </div>
        </section>

        {/* Definitions */}
        <section aria-labelledby="vc-def" className="flex flex-col gap-4">
          <h2 id="vc-def" className={H2}>Definitions</h2>
          <dl className="grid grid-cols-1 md:grid-cols-[220px_minmax(0,1fr)] gap-x-8 gap-y-2 text-sm max-w-[1100px]">
            {Object.entries(data.definitions).map(([k, v]) => (
              <React.Fragment key={k}>
                <dt className="font-medium text-text">{k.replace(/_/g, ' ')}</dt>
                <dd className="text-text-2">{v}</dd>
              </React.Fragment>
            ))}
          </dl>
        </section>

        {/* Cross-reference */}
        <section aria-labelledby="vc-x" className="flex flex-col gap-4">
          <h2 id="vc-x" className={H2}>Cross-reference: analyse.py incremental table</h2>
          <p className={LEAD}>
            From {data.cross_reference.source}. {data.cross_reference.note}
          </p>
          <p className={`text-sm max-w-[80ch] ${data.cross_reference.on_disk_matches ? 'text-text-3' : 'text-warning-ink'}`}>
            {data.cross_reference.on_disk_note}
          </p>
          <div className="border border-line rounded overflow-x-auto">
            <table className="w-full min-w-[860px] text-sm border-collapse">
              <thead className="bg-surface-2 border-b border-line">
                <tr>
                  <th className={TH}>Cohort</th>
                  <th className={TH}>Through</th>
                  <th className={THR}>Unsafe units</th>
                  <th className={THR}>Stopped by this gate</th>
                  <th className={THR}>Still through</th>
                  <th className={THR}>Safe rejected</th>
                  <th className={THR}>Gate seconds, total</th>
                  <th className={THR}>Median s per unit</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {data.cross_reference.rows.map((r, i) => (
                  <tr key={i}>
                    <td className="px-3 py-2">{COHORT_SHORT[r.cohort as Cohort] ?? r.cohort}</td>
                    <td className="px-3 py-2">{r.through_gate}</td>
                    <td className={TDR}>{r.unsafe_n}</td>
                    <td className={TDR}>{r.unsafe_stopped_marginal}</td>
                    <td className={TDR}>{r.unsafe_remaining}</td>
                    <td className={TDR}>{r.safe_rejected_cum}</td>
                    <td className={TDR}>{r.gate_seconds_total}</td>
                    <td className={TDR}>{r.gate_seconds_median_per_unit}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </div>
  );
};

const CohortTable: React.FC<{
  cohort: Cohort;
  timing: GateTiming[];
  benefit: GateBenefit[];
  unsafe: number;
  judged: number;
}> = ({ cohort, timing, benefit, unsafe, judged }) => (
  <section aria-labelledby={`vc-${cohort}`} className="flex flex-col gap-3">
    <h2 id={`vc-${cohort}`} className={H2}>{COHORT_LABEL[cohort]}</h2>
    <p className="text-sm text-text-2 tabular-nums">
      Execution timing from every eligible run; safety benefit from {judged} distinct judged patches, {unsafe} of
      them unsafe.
    </p>
    <div className="border border-line rounded overflow-x-auto">
      <table className="w-full min-w-[1080px] text-sm border-collapse">
        <thead className="bg-surface-2 border-b border-line">
          <tr>
            <th className={TH} rowSpan={2}>Gate</th>
            <th className="px-3 pt-2 font-medium text-text-2 text-left border-l border-line" colSpan={4}>Execution timing</th>
            <th className="px-3 pt-2 font-medium text-text-2 text-left border-l border-line" colSpan={6}>Safety benefit (judged patches)</th>
          </tr>
          <tr>
            <th className={`${THR} border-l border-line`}>Executions</th>
            <th className={THR}>Untimed</th>
            <th className={THR}>Median s</th>
            <th className={THR}>p95 s</th>
            <th className={`${THR} border-l border-line`}>Reached</th>
            <th className={THR}>Unsafe stopped</th>
            <th className={THR}>Safe stopped</th>
            <th className={THR}>Gate time</th>
            <th className={THR}>Catches per gate-minute</th>
            <th className={THR}>Unsafe still through</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {GATES.map((g, i) => {
            const t = timing[i];
            const b = benefit[i];
            return (
              <tr key={g}>
                <td className="px-3 py-2 font-medium whitespace-nowrap">{GATE_NAME[g]}</td>
                <td className={`${TDR} border-l border-line`}>{t.executions}</td>
                <td className={TDR}>{t.untimed}</td>
                <td className={TDR}>{f1(t.median_s)}</td>
                <td className={TDR}>{f1(t.p95_s)}</td>
                <td className={`${TDR} border-l border-line`}>{b.reached}</td>
                <td className={TDR}>{b.reached ? b.unsafe_stopped : '–'}</td>
                <td className={TDR}>{b.reached ? b.safe_stopped : '–'}</td>
                <td className={TDR}>{b.reached ? minutes(b.seconds) : '–'}</td>
                <td className={TDR}>
                  {b.catches_per_gate_minute == null ? 'undefined' : b.catches_per_gate_minute.toFixed(2)}
                </td>
                <td className={TDR}>{b.unsafe_escaping_after}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
    {benefit.some((b) => b.tool_error_stopped > 0) && (
      <p className="text-sm text-text-3">
        Tool errors or timeouts stopped{' '}
        {benefit.reduce((s, b) => s + b.tool_error_stopped, 0)} patch(es); they are not counted as safety catches.
      </p>
    )}
  </section>
);
