import React, { useEffect, useMemo, useState } from 'react';
import { AlertTriangle, Search } from 'lucide-react';
import {
  Cohort,
  EvidenceSnapshot,
  GroupEstimate,
  RiskCandidate,
  RiskEstimationData,
} from '../../types/evidence';
import {
  COHORT_LABEL,
  COHORT_SERIES,
  COHORT_SHORT,
  COHORTS,
  EVALUATION_LABEL,
  FEATURE_LABEL,
  MODEL_LABEL,
  num,
  pct,
  secs,
} from '../../components/research/format';
import { IntervalScale, Legend, ReliabilityChart } from '../../components/research/charts';
import { ExtensionUnavailable, Provenance } from '../../components/research/Provenance';

/**
 * Risk Estimation (RQ2). Displays results/risk/risk_estimation.json as exported into the evidence snapshot.
 * Nothing here computes a probability: every figure is read from the analysis output.
 */
export const RiskEstimation: React.FC<{ snapshot: EvidenceSnapshot }> = ({ snapshot }) => {
  const ext = snapshot.risk_estimation;
  if (!ext?.available || !ext.data) {
    return (
      <ExtensionUnavailable
        title="Risk Estimation"
        reason={ext?.reason ?? 'The snapshot has no risk_estimation section. Run python -m tools.risk_model.'}
      />
    );
  }
  return <RiskBody data={ext.data} source={ext.source} sha={ext.sha256_12} />;
};

const SECTION = 'flex flex-col gap-4';
const H2 = 'text-[20px] font-semibold text-text tracking-tight';
const LEAD = 'text-sm text-text-2 leading-relaxed max-w-[75ch]';
const TH = 'px-3 py-2 font-medium text-text-3 text-left';
const THR = 'px-3 py-2 font-medium text-text-3 text-right';
const TD = 'px-3 py-2 text-text';
const TDR = 'px-3 py-2 text-text text-right tabular-nums';

const RiskBody: React.FC<{ data: RiskEstimationData; source: string; sha?: string }> = ({ data, source, sha }) => {
  const [group, setGroup] = useState<string>(data.headline_group);
  const groupLabel = Object.fromEntries(data.groups.map((g) => [g.id, g.label]));
  const est = (c: Cohort, g: string) => data.empirical.estimates.find((e) => e.cohort === c && e.group === g)!;
  const fn = data.funnel;

  return (
    <div className="flex-1 flex flex-col bg-page text-text">
      <div className="w-full max-w-[1440px] mx-auto px-8 pt-8 pb-20 flex flex-col gap-12">
        {/* Header */}
        <header className="flex flex-col gap-2">
          <h1 className="text-[28px] font-bold tracking-tight leading-tight">Risk Estimation</h1>
          <p className="text-base text-text-2 max-w-[75ch]">
            RQ2: can the probability that a patch is unsafe be estimated from the validation evidence the pipeline
            actually records?
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

        {/* Small-sample notice: the limitation that governs every figure on the page */}
        <div role="note" className="flex gap-3 p-4 rounded border border-warning-line/60 bg-warning-tint/40 text-sm">
          <AlertTriangle size={18} className="text-warning-ink flex-shrink-0 mt-0.5" aria-hidden="true" />
          <div className="flex flex-col gap-1">
            <p className="font-semibold text-text">Pilot-scale evidence</p>
            <p className="text-text-2 leading-relaxed">
              {fn.llm.distinct_judged_patches} distinct AI-written patches ({fn.llm.distinct_unsafe} unsafe) and{' '}
              {fn.scripted.distinct_judged_patches} distinct hand-built patches ({fn.scripted.distinct_unsafe} unsafe)
              carry a safe or unsafe oracle label. The labels have not yet had the planned independent two-person
              review. Read every figure here as a pilot measurement, not a production probability.
            </p>
          </div>
        </div>

        {/* A. The estimate */}
        <section aria-labelledby="re-a" className={SECTION}>
          <h2 id="re-a" className={H2}>Estimated probability of an unsafe patch</h2>
          <GroupPicker groups={data.groups} value={group} onChange={setGroup} />
          <div className="grid grid-cols-1 md:grid-cols-2 gap-x-12 gap-y-8 border-y border-line py-6">
            {COHORTS.map((c) => (
              <CohortEstimate key={c} cohort={c} e={est(c, group)} minN={data.min_group_n} groupLabel={groupLabel[group]} />
            ))}
          </div>
          <p className="text-sm text-text-3">
            Method: {data.empirical.method}. Evidence group: {groupLabel[group]}. Unit: one distinct judged patch
            (repeat runs of the same diff count once). Cohorts are estimated separately and never pooled.
          </p>
        </section>

        {/* B. Evidence behind it */}
        <EvidenceSection data={data} group={group} groupLabel={groupLabel[group]} />

        {/* C. How it is calculated */}
        <CalculationSection data={data} group={group} groupLabel={groupLabel[group]} est={est} />

        {/* D. Confidence and reliability */}
        <ReliabilitySection data={data} />

        {/* E. Candidate explorer */}
        <CandidateExplorer data={data} groupLabel={groupLabel} />

        {/* F. Interpretation */}
        <section aria-labelledby="re-f" className={SECTION}>
          <h2 id="re-f" className={H2}>What the results say about RQ2</h2>
          <dl className="grid grid-cols-1 lg:grid-cols-[180px_minmax(0,1fr)] gap-x-8 gap-y-4 border-t border-line pt-4 max-w-[1100px]">
            {data.interpretation.map((i) => (
              <React.Fragment key={i.topic}>
                <dt className="text-sm font-semibold text-text">{TOPIC_LABEL[i.topic] ?? i.topic}</dt>
                <dd className="text-sm text-text-2 leading-relaxed max-w-[80ch]">{i.text}</dd>
              </React.Fragment>
            ))}
          </dl>
          <h3 className="text-base font-semibold mt-4">Limitations</h3>
          <ul className="list-disc pl-5 flex flex-col gap-1 text-sm text-text-2 max-w-[80ch]">
            {data.limitations.map((l) => (
              <li key={l}>{l}</li>
            ))}
          </ul>
        </section>
      </div>
    </div>
  );
};

const TOPIC_LABEL: Record<string, string> = {
  measured: 'What was measured',
  estimated: 'What was estimated',
  observed: 'What was observed',
  reliability: 'How reliable it is',
  inconclusive: 'What remains inconclusive',
};

/* ─── A ─────────────────────────────────────────────────────────────────────────────────────────── */

const GroupPicker: React.FC<{
  groups: Array<{ id: string; label: string }>;
  value: string;
  onChange: (id: string) => void;
}> = ({ groups, value, onChange }) => (
  <div role="radiogroup" aria-label="Evidence group" className="flex flex-wrap gap-1 p-1 rounded bg-surface-2 w-fit max-w-full">
    {groups.map((g) => {
      const on = g.id === value;
      return (
        <button
          key={g.id}
          role="radio"
          aria-checked={on}
          onClick={() => onChange(g.id)}
          className={`h-9 px-3 rounded text-sm transition-colors duration-150 focus-visible:outline-offset-2 ${
            on ? 'bg-page text-text font-semibold shadow-1' : 'text-text-2 hover:text-text hover:bg-control-hover'
          }`}
        >
          {g.label}
        </button>
      );
    })}
  </div>
);

const CohortEstimate: React.FC<{ cohort: Cohort; e: GroupEstimate; minN: number; groupLabel: string }> = ({
  cohort,
  e,
  minN,
  groupLabel,
}) => (
  <div className="flex flex-col gap-2 min-w-0">
    <h3 className="text-sm font-semibold text-text">{COHORT_LABEL[cohort]}</h3>
    {e.status === 'ok' && e.estimate != null && e.ci95_low != null && e.ci95_high != null ? (
      <>
        <p className="text-[32px] font-bold leading-none tabular-nums tracking-tight">{pct(e.estimate)}</p>
        <p className="text-sm text-text tabular-nums">
          {e.unsafe} unsafe of {e.labelled} labelled patches
        </p>
        <p className="text-sm text-text-2 tabular-nums">
          95% Wilson interval for the group rate: {pct(e.ci95_low)} to {pct(e.ci95_high)}
        </p>
        <div className="max-w-[420px] mt-1">
          <IntervalScale
            estimate={e.estimate}
            low={e.ci95_low}
            high={e.ci95_high}
            color={COHORT_SERIES[cohort]}
            label={`${COHORT_SHORT[cohort]}, ${groupLabel}: ${pct(e.estimate)}, 95% interval ${pct(e.ci95_low)} to ${pct(e.ci95_high)}`}
          />
        </div>
      </>
    ) : e.status === 'insufficient' ? (
      <>
        <p className="text-xl font-semibold text-text">Insufficient evidence</p>
        <p className="text-sm text-text-2 tabular-nums">
          {e.unsafe} unsafe of {e.labelled} labelled patches. With fewer than {minN} labelled patches no percentage
          or interval is shown.
        </p>
      </>
    ) : (
      <>
        <p className="text-xl font-semibold text-text">Insufficient evidence to estimate unsafe-patch probability reliably</p>
        <p className="text-sm text-text-2">
          No labelled patch falls in this group.
          {e.group === 'v0_failed' &&
            ' Every patch that failed V0 does not apply or compile, so the oracle labelled it invalid, which is neither safe nor unsafe.'}
        </p>
      </>
    )}
  </div>
);

/* ─── B ─────────────────────────────────────────────────────────────────────────────────────────── */

const EvidenceSection: React.FC<{ data: RiskEstimationData; group: string; groupLabel: string }> = ({
  data,
  group,
  groupLabel,
}) => {
  const summ = (c: Cohort) => data.empirical.group_feature_summary.find((s) => s.cohort === c && s.group === group)!;
  const cell = (c: Cohort, f: string) => {
    const s = summ(c);
    if (s.n === 0) return 'no patches';
    if (f === 'gate_fail') return 'defines the group';
    if (f === 'log_diff_lines') return `median ${s.diff_lines_median} lines, max ${s.diff_lines_max}`;
    const k = (s as unknown as Record<string, number>)[f];
    return `${k} of ${s.n}`;
  };
  const coef = data.model.coefficients_all_data;
  return (
    <section aria-labelledby="re-b" className={SECTION}>
      <h2 id="re-b" className={H2}>Evidence behind the estimate</h2>
      <p className={LEAD}>
        The group rate above uses the gate outcomes only. The logistic model uses all five inputs below. Values are
        counted over the labelled distinct patches in “{groupLabel}”.
      </p>
      <div className="border border-line rounded overflow-x-auto">
        <table className="w-full min-w-[860px] text-sm border-collapse">
          <thead className="bg-surface-2 border-b border-line">
            <tr>
              <th className={TH}>Evidence</th>
              <th className={TH}>Definition</th>
              <th className={TH}>Used by</th>
              <th className={THR}>{COHORT_SHORT.llm}</th>
              <th className={THR}>{COHORT_SHORT.scripted}</th>
              <th className={THR}>Fitted weight</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {data.model.features.map((f) => (
              <tr key={f}>
                <td className={`${TD} font-medium`}>{FEATURE_LABEL[f] ?? f}</td>
                <td className="px-3 py-2 text-text-2">{data.model.feature_definitions[f]}</td>
                <td className="px-3 py-2 text-text-2">{f === 'gate_fail' ? 'Group rate and logistic model' : 'Logistic model'}</td>
                <td className={TDR}>{cell('llm', f)}</td>
                <td className={TDR}>{cell('scripted', f)}</td>
                <td className={TDR}>{coef[f] >= 0 ? '+' : '−'}{Math.abs(coef[f]).toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-sm text-text-3 max-w-[90ch]">
        Fitted weight: standardised logistic coefficient. {data.model.coefficients_note} A weight is the fit's own
        statement, not evidence that the factor raises risk: the out-of-sample checks in “Confidence and reliability”
        decide whether the inputs help.
      </p>
      <h3 className="text-base font-semibold mt-2">Considered and not used</h3>
      <dl className="grid grid-cols-1 md:grid-cols-[240px_minmax(0,1fr)] gap-x-8 gap-y-2 text-sm max-w-[1100px]">
        {data.model.not_used.map((n) => (
          <React.Fragment key={n.id}>
            <dt className="font-medium text-text">{n.label}</dt>
            <dd className="text-text-2">{n.reason}</dd>
          </React.Fragment>
        ))}
      </dl>
    </section>
  );
};

/* ─── C ─────────────────────────────────────────────────────────────────────────────────────────── */

const CalculationSection: React.FC<{
  data: RiskEstimationData;
  group: string;
  groupLabel: string;
  est: (c: Cohort, g: string) => GroupEstimate;
}> = ({ data, group, groupLabel, est }) => {
  const line = (c: Cohort) => {
    const e = est(c, group);
    if (e.labelled === 0) return `${COHORT_SHORT[c]}: 0 / 0, undefined (no labelled patch)`;
    if (e.status !== 'ok') return `${COHORT_SHORT[c]}: ${e.unsafe} / ${e.labelled}, counts only (fewer than ${data.min_group_n} labelled)`;
    return `${COHORT_SHORT[c]}: ${e.unsafe} / ${e.labelled} = ${num(e.estimate)}`;
  };
  const coef = data.model.coefficients_all_data;
  return (
    <section aria-labelledby="re-c" className={SECTION}>
      <h2 id="re-c" className={H2}>How the probability is calculated</h2>
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-8">
        <div className="flex flex-col gap-3">
          <h3 className="text-base font-semibold">Group rate (the figure at the top)</h3>
          <pre className="text-[13px] leading-relaxed bg-surface-2 border border-line rounded p-4 overflow-x-auto">
{`${data.empirical.formula}

E = "${groupLabel}"
${line('llm')}
${line('scripted')}`}
          </pre>
          <p className="text-sm text-text-2 leading-relaxed">
            An observed frequency: the share of labelled patches with this evidence that the oracle found unsafe.
            The interval is a {data.empirical.interval}:
          </p>
          <pre className="text-[13px] leading-relaxed bg-surface-2 border border-line rounded p-4 overflow-x-auto">
{`centre = (p + z²/2n) / (1 + z²/n)
half   = z / (1 + z²/n) · √( p(1 − p)/n + z²/4n² )
p = k/n, z = 1.96`}
          </pre>
          <p className="text-sm text-text-2 leading-relaxed">{data.min_group_n_rule}</p>
        </div>
        <div className="flex flex-col gap-3">
          <h3 className="text-base font-semibold">Logistic model ({data.model.model_version})</h3>
          <pre className="text-[13px] leading-relaxed bg-surface-2 border border-line rounded p-4 overflow-x-auto">
{`p = 1 / (1 + exp(−(β₀ + Σⱼ βⱼ · zⱼ)))

zⱼ = (xⱼ − mean_train) / sd_train
L2 penalty λ = ${data.model.l2} on βⱼ, β₀ unpenalised

β, fitted on all judged patches (interpretation only):
  intercept        ${num(coef.intercept, 2)}
${data.model.features.map((f) => `  ${f.padEnd(16)} ${num(coef[f], 2)}`).join('\n')}`}
          </pre>
          <p className="text-sm text-text-2 leading-relaxed">
            A model-predicted probability, not an observed frequency. It is shown only for labelled patches, and
            only as an out-of-fold prediction: the patch's own fault was held out of the fit that scored it.
            Evaluation: {data.model.evaluation_method}.
          </p>
        </div>
      </div>
      <p className="text-sm text-text-3">
        Unit of analysis: {data.unit_of_analysis}. Labels: hand-built from{' '}
        <code>faults/*/candidates/labels.json</code>; AI-written from <code>results/oracle_report.jsonl</code>.
        Independent adjudication: {data.label_source.independent_adjudication}. Full method:{' '}
        <code>{data.methods_doc}</code>.
      </p>
    </section>
  );
};

/* ─── D ─────────────────────────────────────────────────────────────────────────────────────────── */

const ReliabilitySection: React.FC<{ data: RiskEstimationData }> = ({ data }) => {
  const rel = data.model.reliability_lofo_pooled;
  const reliabilityText = data.interpretation.find((i) => i.topic === 'reliability')?.text;
  return (
    <section aria-labelledby="re-d" className={SECTION}>
      <h2 id="re-d" className={H2}>Confidence and reliability</h2>
      <dl className="grid grid-cols-1 md:grid-cols-2 gap-x-12 gap-y-3 text-sm max-w-[1100px]">
        <div>
          <dt className="font-semibold text-text">Interval for a group rate</dt>
          <dd className="text-text-2 leading-relaxed mt-1">
            The Wilson interval says how precisely the group's unsafe share is known from its sample. It is not a
            range for any single patch: one patch is either unsafe or not.
          </dd>
        </div>
        <div>
          <dt className="font-semibold text-text">Reliability of a per-patch prediction</dt>
          <dd className="text-text-2 leading-relaxed mt-1">
            Whether model probabilities match outcomes on patches the model was not fitted on. Measured below by
            Brier score, AUC and a reliability table.
          </dd>
        </div>
      </dl>

      <h3 className="text-base font-semibold mt-2">Out-of-sample accuracy</h3>
      <div className="border border-line rounded overflow-x-auto">
        <table className="w-full min-w-[860px] text-sm border-collapse">
          <thead className="bg-surface-2 border-b border-line">
            <tr>
              <th className={TH}>Evaluation</th>
              <th className={TH}>Scored cohort</th>
              <th className={TH}>Model</th>
              <th className={THR}>Patches</th>
              <th className={THR}>Unsafe</th>
              <th className={THR}>Brier</th>
              <th className={THR}>Brier skill</th>
              <th className={THR}>Log loss</th>
              <th className={THR}>AUC</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {data.model.metrics.map((m, i) => (
              <tr key={i} className={m.model === 'base_rate' ? 'text-text-2' : ''}>
                <td className={`${TD} ${m.model === 'base_rate' ? 'font-medium' : 'text-text-3'}`}>
                  {m.model === 'base_rate' ? EVALUATION_LABEL[m.evaluation] : ''}
                </td>
                <td className={TD}>{m.model === 'base_rate' ? COHORT_SHORT[m.cohort] : ''}</td>
                <td className={TD}>{MODEL_LABEL[m.model]}</td>
                <td className={TDR}>{m.n}</td>
                <td className={TDR}>{m.unsafe}</td>
                <td className={TDR}>{num(m.brier)}</td>
                <td className={TDR}>{num(m.brier_skill)}</td>
                <td className={TDR}>{num(m.log_loss)}</td>
                <td className={TDR}>{num(m.auc)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-sm text-text-3 max-w-[90ch]">
        Brier: mean squared error of the probability, lower is better. Brier skill: improvement over the base rate,
        above 0 means the evidence helps. AUC: chance an unsafe patch is ranked above a safe one, 0.5 is chance.
      </p>

      <h3 className="text-base font-semibold mt-2">Among patches that passed all four gates</h3>
      <p className={LEAD}>
        The case the decision depends on: the gates let these through, so any useful risk estimate has to separate
        them. {reliabilityText}
      </p>
      <div className="border border-line rounded overflow-x-auto max-w-[760px]">
        <table className="w-full text-sm border-collapse">
          <thead className="bg-surface-2 border-b border-line">
            <tr>
              <th className={TH}>Evaluation</th>
              <th className={TH}>Cohort</th>
              <th className={THR}>Patches</th>
              <th className={THR}>Unsafe</th>
              <th className={THR}>AUC (logistic)</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {data.model.allpass_separation.map((a, i) => (
              <tr key={i}>
                <td className={TD}>{EVALUATION_LABEL[a.evaluation]}</td>
                <td className={TD}>{COHORT_SHORT[a.cohort]}</td>
                <td className={TDR}>{a.n}</td>
                <td className={TDR}>{a.unsafe}</td>
                <td className={TDR}>{num(a.auc)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h3 className="text-base font-semibold mt-2">Calibration of the logistic model</h3>
      <p className={LEAD}>
        Out-of-fold predictions from leave one fault out on both cohorts, grouped into bins of predicted
        probability. A well-calibrated model sits on the dashed line. Circle area grows with the number of patches.
      </p>
      <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,420px)_minmax(0,1fr)] gap-8 items-start">
        <div className="flex flex-col gap-2">
          <Legend items={COHORTS.map((c) => ({ name: COHORT_SHORT[c], color: COHORT_SERIES[c] }))} />
          <ReliabilityChart
            label="Reliability plot of out-of-fold logistic predictions against the observed unsafe share, per cohort"
            points={rel.map((r) => ({
              series: r.cohort,
              color: COHORT_SERIES[r.cohort],
              predicted: r.mean_predicted,
              observed: r.observed_unsafe,
              n: r.n,
            }))}
          />
        </div>
        <div className="border border-line rounded overflow-x-auto">
          <table className="w-full text-sm border-collapse">
            <thead className="bg-surface-2 border-b border-line">
              <tr>
                <th className={TH}>Cohort</th>
                <th className={TH}>Predicted bin</th>
                <th className={THR}>Patches</th>
                <th className={THR}>Mean predicted</th>
                <th className={THR}>Observed unsafe</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {rel.map((r, i) => (
                <tr key={i}>
                  <td className={TD}>{COHORT_SHORT[r.cohort]}</td>
                  <td className={`${TD} tabular-nums`}>
                    {r.bin_low.toFixed(1)} to {r.bin_high.toFixed(1)}
                  </td>
                  <td className={TDR}>{r.n}</td>
                  <td className={TDR}>{num(r.mean_predicted)}</td>
                  <td className={TDR}>{num(r.observed_unsafe)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
};

/* ─── E ─────────────────────────────────────────────────────────────────────────────────────────── */

const candKey = (c: RiskCandidate) => `${c.run_id}|${c.candidate_id}`;

function readSelected(): string | null {
  try {
    return new URLSearchParams(window.location.search).get('candidate');
  } catch {
    return null;
  }
}

function writeSelected(key: string | null) {
  const url = new URL(window.location.href);
  if (key) url.searchParams.set('candidate', key);
  else url.searchParams.delete('candidate');
  window.history.replaceState(window.history.state, '', url.toString());
}

const STATUS_CHAR: Record<string, string> = { pass: 'P', fail: 'F', error: 'E', timeout: 'T', not_run: '–' };

const CandidateExplorer: React.FC<{ data: RiskEstimationData; groupLabel: Record<string, string> }> = ({
  data,
  groupLabel,
}) => {
  const [cohort, setCohort] = useState<'all' | Cohort>('all');
  const [fault, setFault] = useState('all');
  const [query, setQuery] = useState('');
  const [selected, setSelected] = useState<string | null>(() => readSelected());

  const faults = useMemo(() => [...new Set(data.candidates.map((c) => c.fault_id))].sort(), [data.candidates]);
  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    return data.candidates
      .filter((c) => cohort === 'all' || c.cohort === cohort)
      .filter((c) => fault === 'all' || c.fault_id === fault)
      .filter((c) => !q || c.candidate_id.toLowerCase().includes(q) || c.run_id.toLowerCase().includes(q))
      .sort(
        (a, b) =>
          COHORTS.indexOf(a.cohort) - COHORTS.indexOf(b.cohort) ||
          a.fault_id.localeCompare(b.fault_id) ||
          a.run_id.localeCompare(b.run_id) ||
          a.candidate_id.localeCompare(b.candidate_id),
      );
  }, [data.candidates, cohort, fault, query]);

  const current = data.candidates.find((c) => candKey(c) === selected) ?? rows[0] ?? null;
  useEffect(() => {
    writeSelected(selected);
  }, [selected]);

  const counts = { all: data.candidates.length, llm: 0, scripted: 0 } as Record<string, number>;
  data.candidates.forEach((c) => (counts[c.cohort] += 1));

  return (
    <section aria-labelledby="re-e" className={SECTION}>
      <h2 id="re-e" className={H2}>Candidate risk explorer</h2>
      <p className={LEAD}>
        Every recorded research unit ({data.candidates.length}). A candidate gets the observed rate of its evidence
        group within its own cohort, which is a rate for the group and not a probability specific to the patch. The
        model score appears only for labelled patches.
      </p>

      <div className="flex flex-wrap items-end gap-3">
        <div role="radiogroup" aria-label="Cohort" className="flex gap-1 p-1 rounded bg-surface-2">
          {(['all', ...COHORTS] as const).map((c) => (
            <button
              key={c}
              role="radio"
              aria-checked={cohort === c}
              onClick={() => setCohort(c)}
              className={`h-8 px-3 rounded text-sm transition-colors duration-150 focus-visible:outline-offset-2 ${
                cohort === c ? 'bg-page text-text font-semibold shadow-1' : 'text-text-2 hover:text-text hover:bg-control-hover'
              }`}
            >
              {c === 'all' ? 'All' : COHORT_SHORT[c]} <span className="tabular-nums text-text-3">{counts[c]}</span>
            </button>
          ))}
        </div>
        <label className="flex flex-col gap-1 text-sm text-text-2">
          Fault
          <select
            value={fault}
            onChange={(e) => setFault(e.target.value)}
            className="h-9 px-2 rounded border border-line-strong bg-page text-text text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus"
          >
            <option value="all">All faults</option>
            {faults.map((f) => (
              <option key={f} value={f}>
                {f}
              </option>
            ))}
          </select>
        </label>
        <label className="relative flex items-center">
          <span className="sr-only">Search candidates by candidate or run id</span>
          <Search size={14} className="absolute left-2.5 text-text-3" aria-hidden="true" />
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search candidate or run id"
            className="h-9 w-[260px] pl-8 pr-2 rounded border border-line-strong bg-page text-text text-sm placeholder:text-text-3 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus"
          />
        </label>
        <span className="text-sm text-text-3 tabular-nums pb-2">{rows.length} shown</span>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_minmax(0,460px)] gap-6 items-start">
        <div className="border border-line rounded overflow-auto max-h-[620px]">
          {rows.length === 0 ? (
            <div className="p-6 text-sm text-text-2">
              No candidate matches “{query}”.{' '}
              <button className="underline text-text" onClick={() => setQuery('')}>
                Clear the search
              </button>
            </div>
          ) : (
            <table className="w-full min-w-[640px] text-sm border-collapse">
              <thead className="bg-surface-2 border-b border-line sticky top-0">
                <tr>
                  <th className={TH}>Candidate</th>
                  <th className={TH}>Fault</th>
                  <th className={TH} title="P pass, F fail, E error, T timeout, – not run">
                    V0 V1 V2 V3
                  </th>
                  <th className={TH}>Decision</th>
                  <th className={THR}>Group rate</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((c) => {
                  const on = current && candKey(c) === candKey(current);
                  return (
                    <tr
                      key={candKey(c)}
                      tabIndex={0}
                      aria-selected={!!on}
                      onClick={() => setSelected(candKey(c))}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault();
                          setSelected(candKey(c));
                        }
                      }}
                      className={`cursor-pointer border-b border-line last:border-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-focus ${
                        on ? 'bg-selected' : 'hover:bg-surface-2'
                      }`}
                    >
                      <td className="px-3 py-2 min-w-0 max-w-[280px]">
                        <div className="font-medium text-text truncate" title={c.candidate_id}>{c.candidate_id}</div>
                        <div className="text-xs text-text-3 truncate" title={c.run_id}>{c.run_id}</div>
                      </td>
                      <td className={TD}>{c.fault_id}</td>
                      <td className="px-3 py-2 font-mono text-text-2 tracking-[0.3em] whitespace-nowrap" aria-label={(['V0', 'V1', 'V2', 'V3'] as const).map((g) => `${g} ${c.gates[g].status}`).join(', ')}>
                        {(['V0', 'V1', 'V2', 'V3'] as const).map((g) => STATUS_CHAR[c.gates[g].status] ?? '?').join('')}
                      </td>
                      <td className="px-3 py-2 text-text-2 whitespace-nowrap">{c.decision ?? '–'}</td>
                      <td className={TDR}>
                        {c.group_estimate.status === 'ok' ? pct(c.group_estimate.estimate) : <span className="text-text-3">unavailable</span>}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
        {current && <CandidateDetail c={current} groupLabel={groupLabel} minN={data.min_group_n} />}
      </div>
    </section>
  );
};

const CandidateDetail: React.FC<{ c: RiskCandidate; groupLabel: Record<string, string>; minN: number }> = ({
  c,
  groupLabel,
  minN,
}) => {
  const g = c.group_estimate;
  return (
    <aside aria-label="Selected candidate" className="border border-line rounded p-5 flex flex-col gap-5 bg-surface xl:sticky xl:top-20">
      <div className="min-w-0">
        <h3 className="text-base font-semibold text-text break-all">{c.candidate_id}</h3>
        <p className="text-sm text-text-3 break-all">{c.run_id}</p>
        <p className="text-sm text-text-2 mt-1">
          {c.fault_id} · {COHORT_SHORT[c.cohort]} · {c.model ?? 'hand-built (no model)'} · diagnosis {c.diag_mode ?? '–'}
        </p>
      </div>

      <div>
        <h4 className="text-sm font-semibold mb-1">Gate results</h4>
        <table className="w-full text-sm">
          <tbody>
            {(['V0', 'V1', 'V2', 'V3'] as const).map((gate) => (
              <tr key={gate}>
                <td className="py-0.5 pr-3 font-medium w-12">{gate}</td>
                <td className="py-0.5 text-text-2">{c.gates[gate].status.replace('_', ' ')}</td>
                <td className="py-0.5 text-right tabular-nums text-text-2">
                  {c.gates[gate].status === 'not_run' ? '' : secs(c.gates[gate].seconds)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div>
        <h4 className="text-sm font-semibold mb-1">Deterministic policy</h4>
        <p className="text-sm text-text">
          {c.decision ?? '–'} <span className="text-text-2">· tier {c.tier ?? '–'}</span>
        </p>
        <p className="text-xs text-text-3 mt-1">A rule-based tier from config/decision.yaml. It is not a probability.</p>
      </div>

      <div>
        <h4 className="text-sm font-semibold mb-1">Statistical estimate</h4>
        <p className="text-sm text-text-2">Evidence group: {groupLabel[c.evidence_group] ?? c.evidence_group}</p>
        {g.status === 'ok' ? (
          <p className="text-sm text-text mt-1 tabular-nums">
            Group rate for {c.cohort === 'llm' ? 'AI-written' : 'hand-built'} patches: {pct(g.estimate)} ({g.unsafe} of {g.labelled}),
            95% interval {pct(g.ci95_low)} to {pct(g.ci95_high)}
          </p>
        ) : (
          <p className="text-sm text-text mt-1 tabular-nums">
            Estimate unavailable:{' '}
            {g.labelled === 0
              ? 'no labelled patch shares this evidence.'
              : `${g.unsafe} of ${g.labelled} labelled patches share this evidence, fewer than ${minN}.`}
          </p>
        )}
        <p className="text-xs text-text-3 mt-1">The rate of the group, not a probability specific to this patch.</p>
        <p className="text-sm text-text mt-3 tabular-nums">
          Model score: {c.model_probability != null ? num(c.model_probability) : 'Estimate unavailable'}
        </p>
        <p className="text-xs text-text-3 mt-1">{c.model_probability_note}</p>
      </div>

      <div>
        <h4 className="text-sm font-semibold mb-1">Evidence inputs</h4>
        <dl className="grid grid-cols-[minmax(0,1fr)_auto] gap-x-4 gap-y-0.5 text-sm">
          <dt className="text-text-2">Changed lines</dt>
          <dd className="text-right tabular-nums">{c.inputs.diff_lines ?? '–'}</dd>
          <dt className="text-text-2">Files touched</dt>
          <dd className="text-right tabular-nums">{c.inputs.files_touched.length}</dd>
          <dt className="text-text-2">New Semgrep findings</dt>
          <dd className="text-right tabular-nums">{c.inputs.new_findings_count}</dd>
          <dt className="text-text-2">Sensitive path</dt>
          <dd className="text-right">{c.inputs.sensitive_matches.length ? 'yes' : 'no'}</dd>
        </dl>
        {c.inputs.files_touched.length > 0 && (
          <ul className="mt-2 text-xs text-text-3 flex flex-col gap-0.5">
            {c.inputs.files_touched.map((f) => (
              <li key={f} className="break-all font-mono">{f}</li>
            ))}
          </ul>
        )}
      </div>

      <div className="border-t border-line pt-4">
        <h4 className="text-sm font-semibold mb-1">Independent post-run oracle classification</h4>
        <p className="text-sm text-text">{c.oracle_label ?? 'No oracle label'}</p>
        <p className="text-xs text-text-3 mt-1">
          Assigned offline after the run. It is never an input to the estimate or to the decision.
        </p>
      </div>
    </aside>
  );
};
