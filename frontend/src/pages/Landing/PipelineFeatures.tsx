import React from 'react';
import { Hammer, ListChecks, ScanSearch, ShieldCheck, Target } from 'lucide-react';
import InkOrbitFeatures from '../../components/ui/ink-orbit-features';
import { EvidenceSnapshot } from '../../types/evidence';

// The component's palette mapped onto the app's theme tokens, so it follows the
// site's light/dark toggle rather than its own prefers-color-scheme check.
// Inline custom properties override both of its built-in themes.
const TOKEN_STYLE = {
  '--ib-page': 'var(--surface-2)',
  '--ib-hatch': 'color-mix(in srgb, var(--text) 6%, transparent)',
  '--ib-paper': 'var(--page)',
  '--ib-card': 'var(--surface)',
  '--ib-raise': 'var(--page)',
  '--ib-ink': 'var(--text)',
  '--ib-soft': 'var(--text-2)',
  '--ib-muted': 'var(--text-3)',
  '--ib-faint': 'var(--text-3)',
  '--ib-line': 'var(--line)',
  '--ib-line-strong': 'color-mix(in srgb, var(--line-strong) 55%, var(--line))',
  '--ib-bracket': 'var(--line-strong)',
  '--ib-inv': 'var(--action)',
  '--ib-inv-ink': 'var(--on-action)',
  '--ib-shadow': 'var(--shadow-2)',
  '--ib-sans': 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif',
  '--ib-mono': 'ui-monospace, "SF Mono", Menlo, Consolas, monospace',
} as React.CSSProperties;

// Lucide icons drawn inside SVG tiles: offset by half their size to centre them.
const gateGlyph = (Icon: typeof Hammer) => (
  <g transform="translate(-7,-7)">
    <Icon size={14} strokeWidth={1.75} />
  </g>
);

const GATES = ['V0', 'V1', 'V2', 'V3'] as const;

export const PipelineFeatures: React.FC<{ snapshot: EvidenceSnapshot }> = ({ snapshot }) => {
  const meta = snapshot.metadata;
  const stops = snapshot.first_stop_distribution ?? {};
  const units = meta.total_units;

  // Units still in after each gate, from the recorded first-stop distribution.
  const remaining = GATES.reduce<number[]>((acc, g) => [...acc, acc[acc.length - 1] - (stops[g] ?? 0)], [units]);
  const pointNames = ['start', 'after V0', 'after V1', 'after V2', 'after V3'];
  const passAll = remaining[remaining.length - 1];

  return (
    <section aria-label="Pipeline at a glance" className="w-full border-b border-line">
      <InkOrbitFeatures
        brand="AutoImmune"
        mark={<ShieldCheck size={16} strokeWidth={1.75} />}
        tag="Pipeline at a glance"
        title={'Every patch *earns*\nits deploy'}
        style={TOKEN_STYLE}
        flow={{
          nodes: [
            { badge: 'F01', name: 'F01 · customer search null guard' },
            { badge: 'F04', name: 'F04 · catalog health indicator config' },
            { badge: 'F06', name: 'F06 · discount threshold boundary' },
          ],
          reportCount: meta.total_evidence_rows,
          live: false,
          reportTitle: (n) => `${n} EVIDENCE ROWS`,
          ariaLabel: 'Incidents from three seeded faults flow through AutoImmune into recorded evidence rows',
        }}
        collaboration={{
          title: 'Detect and diagnose',
          description:
            'Rule-based checks on the running service raise an incident for each seeded fault. A model is used only to diagnose it and draft candidate patches.',
        }}
        reports={{
          title: 'One evidence row per candidate',
          description: `Gate results, the decision and the deploy outcome are recorded for every candidate: ${meta.total_evidence_rows} rows across ${meta.total_runs_recorded} runs.`,
        }}
        integrations={{
          title: 'Four gates, in order',
          description:
            'Each candidate stops at its first failing gate. Maven and Semgrep run in Docker with --network none, and a timeout or tool error is not a pass.',
          tools: ['V0 · compile', 'V1 · target test', 'V2 · full suite', 'V3 · Semgrep'],
          glyphs: [gateGlyph(Hammer), gateGlyph(Target), gateGlyph(ListChecks), gateGlyph(ScanSearch)],
          activeText: (t) => 'gate ' + t.toLowerCase(),
          idleText: 'V0 → V3',
        }}
        insights={{
          title: 'Gate attrition',
          description: `Of ${units} deduplicated units, how many are still in after each gate. ${passAll} pass all four.`,
          values: remaining,
          forecastFrom: remaining.length,
          pointLabel: (i, v) => `${pointNames[i] ?? ''} · ${v} left`,
        }}
      />
    </section>
  );
};
