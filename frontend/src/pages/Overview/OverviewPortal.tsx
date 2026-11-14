import React from 'react';
import GlyphPortal from '../../components/ui/glyph-portal';

interface OverviewPortalProps {
  runs: number;
  evaluations: number;
}

const STEPS = [
  {
    no: '01',
    title: 'Observe and diagnose',
    body: 'Rule-based checks raise the incident. A model is used only to diagnose it and draft three candidate patches.',
  },
  {
    no: '02',
    title: 'Gate V0 to V3',
    body: 'Compile, the target test, the full suite and new-only Semgrep findings, run in Docker with no network.',
  },
  {
    no: '03',
    title: 'Decide and recover',
    body: 'REJECT, ESCALATE or AUTO_APPLY. Deploy, watch the health window, then promote or roll back.',
  },
];

// Positions use the --gp-word-top / --gp-word-bottom vars the portal sets.
const CSS = `
  [data-ov-portal] [data-gp-caption]{inset:calc(var(--gp-word-bottom,50%) + 84px) 24px auto;justify-content:center;}
  [data-ov-portal] [data-gp-hint]{display:none;}
  [data-ov-portal] [data-gp-enter]{min-height:44px;padding:0 18px;gap:20px;background:var(--action);color:var(--on-action);border-radius:6px;font-size:14px;font-weight:600;}
  [data-ov-portal] [data-gp-enter]:hover{background:var(--action-hover);}
  [data-ov-portal] [data-gp-touch-picker]{top:auto;bottom:18px;}
  [data-ov-portal] [data-gp-content]{padding:5rem clamp(1.25rem,5vw,5rem);}
  [data-ov-eyebrow]{position:absolute;inset:auto 24px calc(100% - var(--gp-word-top,35%) + 28px);margin:0;text-align:center;}
  [data-ov-support]{position:absolute;inset:calc(var(--gp-word-bottom,50%) + 28px) 24px auto;margin:0;text-align:center;}
`;

export const OverviewPortal: React.FC<OverviewPortalProps> = ({ runs, evaluations }) => (
  <div data-ov-portal>
    <style>{CSS}</style>
    <GlyphPortal
      word="VALIDATE"
      fontWeight={900}
      scrollLength={2.4}
      topOffset={56}
      enterLabel="Enter the study"
      style={{
        '--gp-paper': 'var(--page)',
        '--gp-ink': 'var(--text)',
        '--gp-field': 'var(--text)',
        '--gp-foreground': 'var(--page)',
        fontFamily: 'inherit',
      }}
      background={<div style={{ position: 'absolute', inset: 0, background: 'var(--text)' }} />}
      front={
        <>
          <p data-ov-eyebrow className="text-xs font-mono uppercase tracking-[0.3em] text-text">
            Validation-gated self-healing
          </p>
          <p data-ov-support className="text-sm sm:text-base text-text">
            Scroll to step inside the pipeline.
          </p>
        </>
      }
    >
      <div className="w-full max-w-6xl mx-auto flex flex-col gap-10">
        <div className="flex flex-col gap-3">
          <span className="text-xs font-mono uppercase tracking-[0.25em] text-page/75">Research question</span>
          <h2 className="text-[26px] sm:text-[34px] font-semibold leading-tight max-w-3xl">
            How much execution evidence lets an AI-generated patch deploy without human review, and what does
            each gate catch?
          </h2>
          <p className="text-sm text-page/75 tabular-nums">
            {runs} recorded runs · {evaluations} candidate evaluations
          </p>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-7 md:gap-12">
          {STEPS.map((s) => (
            <div key={s.no} className="border-t border-page/25 pt-4">
              <h3 className="text-lg font-semibold">
                <span className="font-mono text-xs tracking-widest mr-2 text-page/75">{s.no}</span>
                {s.title}
              </h3>
              <p className="mt-2 text-[15px] leading-relaxed text-page/75">{s.body}</p>
            </div>
          ))}
        </div>
      </div>
    </GlyphPortal>
  </div>
);
