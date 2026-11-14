import React, { useEffect, useRef, useState } from 'react';

/**
 * Small SVG charts for the research pages. Values are labelled directly on every bar and point, so nothing
 * depends on hover, and each chart has an aria-label summarising what it shows. Colours are series tokens.
 */

function useWidth<T extends HTMLElement>(): [React.RefObject<T>, number] {
  const ref = useRef<T>(null);
  const [w, setW] = useState(0);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setW(el.clientWidth));
    ro.observe(el);
    setW(el.clientWidth);
    return () => ro.disconnect();
  }, []);
  return [ref as React.RefObject<T>, w];
}

const AXIS = 'var(--line-strong)';
const GRID = 'var(--line)';
const TEXT2 = 'var(--text-2)';
const TEXT3 = 'var(--text-3)';

function niceMax(v: number): number {
  if (v <= 0) return 1;
  const p = Math.pow(10, Math.floor(Math.log10(v)));
  for (const m of [1, 2, 2.5, 5, 10]) if (v <= m * p) return m * p;
  return 10 * p;
}

/* ─── Interval on a 0–100% scale (one group rate and its 95% interval) ──────────────────────────── */

export const IntervalScale: React.FC<{
  estimate: number;
  low: number;
  high: number;
  color: string;
  label: string;
}> = ({ estimate, low, high, color, label }) => {
  const [ref, w] = useWidth<HTMLDivElement>();
  const pad = 8;
  const x = (v: number) => pad + v * Math.max(0, w - pad * 2);
  return (
    <div ref={ref} className="w-full">
      {w > 0 && (
        <svg width={w} height={38} role="img" aria-label={label}>
          <line x1={x(0)} x2={x(1)} y1={12} y2={12} stroke={AXIS} />
          {[0, 0.25, 0.5, 0.75, 1].map((t) => (
            <g key={t}>
              <line x1={x(t)} x2={x(t)} y1={8} y2={16} stroke={AXIS} />
              <text x={x(t)} y={32} textAnchor={t === 0 ? 'start' : t === 1 ? 'end' : 'middle'} fontSize={11} fill={TEXT3}>
                {t * 100}%
              </text>
            </g>
          ))}
          <rect x={x(low)} y={8} width={Math.max(2, x(high) - x(low))} height={8} rx={2} fill={color} opacity={0.35} />
          <line x1={x(low)} x2={x(low)} y1={5} y2={19} stroke={color} strokeWidth={2} />
          <line x1={x(high)} x2={x(high)} y1={5} y2={19} stroke={color} strokeWidth={2} />
          <circle cx={x(estimate)} cy={12} r={5} fill={color} stroke="var(--page)" strokeWidth={1.5} />
        </svg>
      )}
    </div>
  );
};

/* ─── Reliability (calibration) plot ────────────────────────────────────────────────────────────── */

export interface ReliabilityPoint {
  series: string;
  color: string;
  predicted: number;
  observed: number;
  n: number;
}

export const ReliabilityChart: React.FC<{ points: ReliabilityPoint[]; label: string }> = ({ points, label }) => {
  const [ref, w] = useWidth<HTMLDivElement>();
  const size = Math.min(w, 420);
  const m = { l: 44, r: 12, t: 12, b: 40 };
  const pw = size - m.l - m.r;
  const ph = size - m.t - m.b;
  const x = (v: number) => m.l + v * pw;
  const y = (v: number) => m.t + (1 - v) * ph;
  const ticks = [0, 0.2, 0.4, 0.6, 0.8, 1];
  return (
    <div ref={ref} className="w-full">
      {size > 0 && (
        <svg width={size} height={size} role="img" aria-label={label}>
          {ticks.map((t) => (
            <g key={t}>
              <line x1={x(0)} x2={x(1)} y1={y(t)} y2={y(t)} stroke={GRID} />
              <line x1={x(t)} x2={x(t)} y1={y(0)} y2={y(1)} stroke={GRID} />
              <text x={x(0) - 6} y={y(t) + 4} textAnchor="end" fontSize={11} fill={TEXT3}>{t.toFixed(1)}</text>
              <text x={x(t)} y={y(0) + 16} textAnchor="middle" fontSize={11} fill={TEXT3}>{t.toFixed(1)}</text>
            </g>
          ))}
          <line x1={x(0)} y1={y(0)} x2={x(1)} y2={y(1)} stroke={AXIS} strokeDasharray="4 4" />
          <text x={x(0.98)} y={y(0.98) + 16} textAnchor="end" fontSize={11} fill={TEXT3}>perfect calibration</text>
          <text x={m.l + pw / 2} y={size - 4} textAnchor="middle" fontSize={11} fill={TEXT2}>Mean predicted probability</text>
          <text transform={`translate(12 ${m.t + ph / 2}) rotate(-90)`} textAnchor="middle" fontSize={11} fill={TEXT2}>
            Observed unsafe share
          </text>
          {points.map((p, i) => (
            <g key={i}>
              <circle cx={x(p.predicted)} cy={y(p.observed)} r={4 + Math.sqrt(p.n) * 1.6} fill={p.color} fillOpacity={0.25} stroke={p.color} strokeWidth={1.5} />
              <text x={x(p.predicted) + 8 + Math.sqrt(p.n) * 1.6} y={y(p.observed) + 4} fontSize={11} fill={TEXT2}>
                n={p.n}
              </text>
            </g>
          ))}
        </svg>
      )}
    </div>
  );
};

/* ─── Horizontal grouped bars, one row per category, one bar per series ─────────────────────────── */

export interface BarSeries {
  name: string;
  color: string;
  values: Array<number | null>;
  /** Optional marker drawn on each bar (for example a p95 tick). */
  markers?: Array<number | null>;
  /** Text printed at the end of each bar; defaults to the value. */
  labels?: string[];
}

export const GroupedBars: React.FC<{
  categories: string[];
  series: BarSeries[];
  unit: string;
  label: string;
  markerLegend?: string;
}> = ({ categories, series, unit, label, markerLegend }) => {
  const [ref, w] = useWidth<HTMLDivElement>();
  const bar = 14;
  const gap = 4;
  const groupGap = 16;
  const m = { l: 36, r: 96, t: 4, b: 28 };
  const groupH = series.length * bar + (series.length - 1) * gap;
  const h = m.t + categories.length * groupH + (categories.length - 1) * groupGap + m.b;
  const all = series.flatMap((s) => [...s.values, ...(s.markers ?? [])]).filter((v): v is number => v != null);
  const max = niceMax(Math.max(0, ...all));
  const pw = Math.max(0, w - m.l - m.r);
  const x = (v: number) => m.l + (v / max) * pw;
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((t) => t * max);
  return (
    <div ref={ref} className="w-full">
      {w > 0 && (
        <svg width={w} height={h} role="img" aria-label={label}>
          {ticks.map((t) => (
            <g key={t}>
              <line x1={x(t)} x2={x(t)} y1={m.t} y2={h - m.b} stroke={GRID} />
              <text x={x(t)} y={h - m.b + 16} textAnchor="middle" fontSize={11} fill={TEXT3}>
                {Number.isInteger(t) ? t : t.toFixed(1)}
              </text>
            </g>
          ))}
          <text x={w - 4} y={h - m.b + 16} textAnchor="end" fontSize={11} fill={TEXT3}>{unit}</text>
          {categories.map((c, ci) => {
            const gy = m.t + ci * (groupH + groupGap);
            return (
              <g key={c}>
                <text x={0} y={gy + groupH / 2 + 4} fontSize={12} fontWeight={600} fill="var(--text)">{c}</text>
                {series.map((s, si) => {
                  const v = s.values[ci];
                  const mk = s.markers?.[ci];
                  const y = gy + si * (bar + gap);
                  const text = s.labels?.[ci] ?? (v == null ? 'not run' : String(v));
                  // Label after the bar and marker; if that runs off the chart, put it between the bar and marker.
                  const est = text.length * 6.2;
                  const after = Math.max(x(v ?? 0), mk != null ? x(mk) : 0) + 6;
                  const fits = after + est <= w - 2;
                  const lx = fits ? after : mk != null ? x(mk) - 6 : w - 2;
                  return (
                    <g key={s.name}>
                      {v != null && <rect x={x(0)} y={y} width={Math.max(1, x(v) - x(0))} height={bar} fill={s.color} />}
                      {mk != null && <line x1={x(mk)} x2={x(mk)} y1={y - 2} y2={y + bar + 2} stroke="var(--text)" strokeWidth={2} />}
                      <text x={lx} y={y + bar - 3} textAnchor={fits ? 'start' : 'end'} fontSize={11} fill={TEXT2}>
                        {text}
                      </text>
                    </g>
                  );
                })}
              </g>
            );
          })}
          <line x1={x(0)} x2={x(0)} y1={m.t} y2={h - m.b} stroke={AXIS} />
          {markerLegend && <title>{markerLegend}</title>}
        </svg>
      )}
    </div>
  );
};

/* ─── Cumulative cost curve: x = cumulative gate time, y = share of unsafe patches stopped ───────── */

export interface CurveSeries {
  name: string;
  color: string;
  points: Array<{ x: number; y: number; label: string }>;
  dash?: string;
}

export const CumulativeChart: React.FC<{
  series: CurveSeries[];
  xLabel: string;
  yLabel: string;
  label: string;
}> = ({ series, xLabel, yLabel, label }) => {
  const [ref, w] = useWidth<HTMLDivElement>();
  const h = 300;
  const m = { l: 48, r: 24, t: 16, b: 44 };
  const maxX = niceMax(Math.max(1, ...series.flatMap((s) => s.points.map((p) => p.x))));
  const pw = Math.max(0, w - m.l - m.r);
  const ph = h - m.t - m.b;
  const x = (v: number) => m.l + (v / maxX) * pw;
  const y = (v: number) => m.t + (1 - v) * ph;
  // Whole-number x ticks where the range allows (25 -> 0, 5, ... 25), else quarters.
  const xSteps = maxX % 5 === 0 ? 5 : 4;
  const xTicks = Array.from({ length: xSteps + 1 }, (_, i) => (i * maxX) / xSteps);
  return (
    <div ref={ref} className="w-full">
      {w > 0 && (
        <svg width={w} height={h} role="img" aria-label={label}>
          {[0, 0.25, 0.5, 0.75, 1].map((t) => (
            <g key={t}>
              <line x1={x(0)} x2={x(maxX)} y1={y(t)} y2={y(t)} stroke={GRID} />
              <text x={m.l - 6} y={y(t) + 4} textAnchor="end" fontSize={11} fill={TEXT3}>{t * 100}%</text>
            </g>
          ))}
          {xTicks.map((t) => (
            <g key={t}>
              <line x1={x(t)} x2={x(t)} y1={y(0)} y2={y(1)} stroke={GRID} />
              <text x={x(t)} y={y(0) + 16} textAnchor="middle" fontSize={11} fill={TEXT3}>
                {Number.isInteger(t) ? t : t.toFixed(1)}
              </text>
            </g>
          ))}
          <text x={m.l + pw / 2} y={h - 6} textAnchor="middle" fontSize={11} fill={TEXT2}>{xLabel}</text>
          <text transform={`translate(12 ${m.t + ph / 2}) rotate(-90)`} textAnchor="middle" fontSize={11} fill={TEXT2}>{yLabel}</text>
          {series.map((s, si) => {
            const pts = [{ x: 0, y: 0, label: '' }, ...s.points];
            return (
              <g key={s.name}>
                <polyline
                  points={pts.map((p) => `${x(p.x)},${y(p.y)}`).join(' ')}
                  fill="none"
                  stroke={s.color}
                  strokeWidth={2}
                  strokeDasharray={s.dash}
                />
                {s.points.map((p, i) => (
                  <g key={i}>
                    <circle cx={x(p.x)} cy={y(p.y)} r={4} fill={s.color} stroke="var(--page)" strokeWidth={1.5} />
                    <text x={x(p.x) + 6} y={y(p.y) + (si === 0 ? -8 : 16)} fontSize={11} fill={TEXT2}>{p.label}</text>
                  </g>
                ))}
              </g>
            );
          })}
        </svg>
      )}
    </div>
  );
};

/* ─── Legend ───────────────────────────────────────────────────────────────────────────────────── */

export const Legend: React.FC<{ items: Array<{ name: string; color: string; dash?: boolean }> }> = ({ items }) => (
  <ul className="flex flex-wrap gap-x-5 gap-y-1 text-sm text-text-2">
    {items.map((it) => (
      <li key={it.name} className="flex items-center gap-2">
        <svg width={18} height={10} aria-hidden="true">
          <line x1={0} x2={18} y1={5} y2={5} stroke={it.color} strokeWidth={it.dash ? 2 : 6} strokeDasharray={it.dash ? '4 3' : undefined} />
        </svg>
        {it.name}
      </li>
    ))}
  </ul>
);
