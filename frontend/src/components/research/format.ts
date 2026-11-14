import { Cohort } from '../../types/evidence';

/** Display order: the AI-written cohort is the research subject, so it comes first everywhere. */
export const COHORTS: Cohort[] = ['llm', 'scripted'];

export const COHORT_LABEL: Record<Cohort, string> = {
  llm: 'AI-written patches',
  scripted: 'Hand-built challenge patches',
};

export const COHORT_SHORT: Record<Cohort, string> = {
  llm: 'AI-written',
  scripted: 'Hand-built',
};

/** Series colour per cohort, from the palette tokens (lead first). */
export const COHORT_SERIES: Record<Cohort, string> = {
  llm: 'var(--series-1)',
  scripted: 'var(--series-2)',
};

export const EVALUATION_LABEL: Record<string, string> = {
  lofo_scripted: 'Leave one fault out, hand-built only',
  scripted_to_llm: 'Fit on hand-built, scored on AI-written',
  lofo_pooled: 'Leave one fault out, both cohorts',
};

export const MODEL_LABEL: Record<string, string> = {
  base_rate: 'Base rate (no evidence)',
  gate_table: 'Gate outcome rate',
  logistic: 'Logistic model',
};

export const FEATURE_LABEL: Record<string, string> = {
  gate_fail: 'Any gate did not pass',
  new_findings: 'New Semgrep findings',
  log_diff_lines: 'Diff size (log of lines)',
  multi_file: 'More than one file touched',
  sensitive_path: 'Sensitive path touched',
};

/** Probability as a percentage with one decimal. Null stays visibly empty. */
export function pct(x: number | null | undefined, digits = 1): string {
  return x == null ? '–' : `${(x * 100).toFixed(digits)}%`;
}

export function num(x: number | null | undefined, digits = 3): string {
  return x == null ? '–' : x.toFixed(digits);
}

export function secs(x: number | null | undefined): string {
  return x == null ? '–' : `${x.toFixed(1)} s`;
}

export function minutes(x: number | null | undefined): string {
  return x == null ? '–' : `${(x / 60).toFixed(1)} min`;
}

export function formatTimestamp(iso: string | undefined): string {
  if (!iso) return 'unknown time';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toISOString().replace('T', ' ').replace(/:\d\d(\.\d+)?Z$/, ' UTC');
}
