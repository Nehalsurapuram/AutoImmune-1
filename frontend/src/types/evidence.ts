export interface GateResult {
  status: "pass" | "fail" | "error" | "timeout" | "not_run";
  seconds?: number;
  exit_code?: number | null;
  log_tail?: string;
  step?: string;
}

export interface GateSet {
  V0?: GateResult;
  V1?: GateResult;
  V2?: GateResult;
  V3?: GateResult;
  [key: string]: GateResult | undefined;
}

export interface DecisionRecord {
  tier?: "low" | "medium" | "high" | string;
  decision?: "AUTO_APPLY" | "ESCALATE" | "REJECT" | string;
  reasons?: string[];
  policy_version?: string;
  patch_meta?: {
    files_touched?: string[];
    diff_lines?: number;
  };
}

export interface CandidateRecord {
  candidate_id: string;
  run_id: string;
  fault_id?: string;
  cohort: "scripted" | "llm";
  diag_mode?: string;
  patch_mode?: string;
  model?: string;
  diff_lines?: number;
  files_touched?: string[];
  gates: GateSet;
  passed_all_gates?: boolean;
  decision: DecisionRecord;
  approval_source?: string | null;
  deployed?: boolean;
  outcome?: "promoted" | "rolled back" | string | null;
  rolled_back?: boolean;
  recovery_s?: number | null;
  first_stop?: string;
  offline_oracle_label?: string;
  offline_oracle_note?: string;
  diff_snippet?: string | null;
  has_deploy_artifact?: boolean;
  has_rollback_artifact?: boolean;
}

export interface TimelineStage {
  id: string;
  name: string;
  status: "pass" | "fail" | "error" | "skipped" | "not_run";
  details: string;
}

export interface IncidentRecord {
  rule?: string;
  rules_fired?: string[];
  kind?: string;
  endpoint?: string;
  status?: number;
  expected?: string;
  actual?: string;
  consecutive_bad_checks?: number;
  evidence?: string[];
  stack_trace?: string | null;
  fault_id?: string;
  failing_check?: any;
}

export interface DiagnosisCause {
  rank: number;
  file: string;
  line: number;
  reason: string;
  evidence?: string;
}

export interface DiagnosisRecord {
  causes?: DiagnosisCause[];
  provider_mode?: string;
  model?: string;
  oracle_localisation?: boolean;
  samples?: any[];
  samples_disagree?: boolean | null;
  top1_hit?: boolean;
  top3_hit?: boolean;
  attempts?: any[];
}

export interface RunRecord {
  run_id: string;
  fault_id?: string;
  diag_mode?: string;
  patch_mode?: string;
  model?: string;
  started_at?: string;
  ended_at?: string;
  outcome?: string;
  config?: any;
  provenance?: {
    git_head?: string;
    git_branch?: string;
    git_dirty?: boolean;
    llm_model?: string;
    llm_base_url?: string;
    code_sha256?: string;
  };
  incident?: IncidentRecord | null;
  diagnosis?: DiagnosisRecord | null;
  candidates: CandidateRecord[];
  deploy_artifact?: any;
  rollback_artifact?: any;
  timeline_stages: TimelineStage[];
  is_excluded?: boolean;
  exclusion_reason?: string;
}

export interface CaseStudy {
  id: string;
  title: string;
  subtitle: string;
  run_id: string;
  candidate_id: string;
  fault_id: string;
  provider: string;
  what_happened: string;
  gates_result: string;
  decision_result: string;
  health_result: string;
  oracle_ground_truth: string;
  research_takeaway: string;
}

export interface EvidenceSnapshot {
  metadata: {
    title: string;
    subtitle: string;
    exported_at: string;
    git: {
      head: string;
      branch: string;
      dirty: boolean;
    };
    analyse_check: {
      status: string;
      exit_code: number;
      message: string;
    };
    acceptance_as_of: string;
    total_runs_recorded: number;
    total_evidence_rows: number;
    total_units: number;
    scripted_units_count: number;
    llm_units_count: number;
    distinct_faults: string[];
    provenance_note: string;
  };
  acceptance: any;
  runs: RunRecord[];
  candidates: CandidateRecord[];
  case_studies: CaseStudy[];
  policies: any[];
  gate_stats: Record<string, any>;
  first_stop_distribution: Record<string, number>;
  deployments: any[];
  rollbacks: any[];
  approvals: any[];
  research_questions: Array<{
    id: string;
    question: string;
    summary: string;
  }>;
  /** Copied verbatim by tools/export_ui_data.py from results/risk/risk_estimation.json. */
  risk_estimation?: ResearchExtension<RiskEstimationData>;
  /** Copied verbatim by tools/export_ui_data.py from results/cost/validation_cost.json. */
  validation_cost?: ResearchExtension<ValidationCostData>;
}

// ─── Research extensions (RQ2 risk estimation, RQ3 validation cost) ───────────
// The console only displays these values; every number is computed by tools/risk_model.py and
// tools/validation_cost.py. Method: docs/research/RISK_AND_COST_METHODS.md.

export type Cohort = 'scripted' | 'llm';
export type GateId = 'V0' | 'V1' | 'V2' | 'V3';

export interface ResearchExtension<T> {
  available: boolean;
  source: string;
  reason?: string;
  sha256_12?: string;
  generator?: string;
  data?: T;
}

export interface SourceArtifact {
  path: string;
  sha256_12: string | null;
}

export type EstimateStatus = 'ok' | 'insufficient' | 'no_labelled_support';

export interface GroupEstimate {
  cohort: Cohort;
  group: string;
  unsafe: number;
  labelled: number;
  status: EstimateStatus;
  estimate: number | null;
  ci95_low: number | null;
  ci95_high: number | null;
}

export interface GroupFeatureSummary {
  cohort: Cohort;
  group: string;
  n: number;
  new_findings: number;
  multi_file: number;
  sensitive_path: number;
  diff_lines_median: number | null;
  diff_lines_max: number | null;
}

export interface CohortFunnel {
  raw_rows: number;
  eligible_rows: number;
  research_units: number;
  labelled_units: number;
  distinct_judged_patches: number;
  distinct_unsafe: number;
  excluded_units: Record<string, number>;
}

export interface ModelMetric {
  evaluation: 'lofo_scripted' | 'scripted_to_llm' | 'lofo_pooled';
  cohort: Cohort;
  model: 'base_rate' | 'gate_table' | 'logistic';
  n: number;
  unsafe: number;
  brier: number;
  brier_skill: number | null;
  log_loss: number;
  auc: number | null;
}

export interface RiskCandidate {
  cohort: Cohort;
  fault_id: string;
  candidate_id: string;
  run_id: string;
  model: string | null;
  diag_mode: string | null;
  gates: Record<GateId, { status: string; seconds: number | null }>;
  tier: string | null;
  decision: string | null;
  evidence_group: string;
  group_estimate: Omit<GroupEstimate, 'cohort' | 'group'>;
  model_probability: number | null;
  model_probability_note: string;
  feature_values: Record<string, number>;
  inputs: {
    diff_lines: number | null;
    files_touched: string[];
    new_findings_count: number;
    sensitive_matches: string[];
  };
  oracle_label: string | null;
  judged: boolean;
}

export interface RiskEstimationData {
  schema_version: number;
  analysis: 'risk_estimation';
  analysis_timestamp: string;
  generator: string;
  methods_doc: string;
  unit_of_analysis: string;
  label_source: {
    scripted: string;
    llm: string;
    unsafe_labels: string[];
    safe_labels: string[];
    excluded_labels: string[];
    independent_adjudication: string;
  };
  funnel: Record<Cohort, CohortFunnel>;
  excluded_run_ids: string[];
  label_conflicts: number;
  min_group_n: number;
  min_group_n_rule: string;
  groups: Array<{ id: string; label: string }>;
  headline_group: string;
  empirical: {
    method: string;
    formula: string;
    interval: string;
    estimates: GroupEstimate[];
    group_feature_summary: GroupFeatureSummary[];
  };
  model: {
    method: string;
    model_version: string;
    l2: number;
    features: string[];
    feature_definitions: Record<string, string>;
    not_used: Array<{ id: string; label: string; reason: string }>;
    standardisation: string;
    coefficients_all_data: Record<string, number>;
    coefficients_note: string;
    evaluation_method: string;
    metrics: ModelMetric[];
    reliability_lofo_pooled: Array<{
      cohort: Cohort;
      bin_low: number;
      bin_high: number;
      n: number;
      mean_predicted: number;
      observed_unsafe: number;
    }>;
    allpass_separation: Array<{ evaluation: string; cohort: Cohort; n: number; unsafe: number; auc: number | null }>;
  };
  interpretation: Array<{ topic: string; text: string }>;
  limitations: string[];
  candidates: RiskCandidate[];
  source_artifacts: SourceArtifact[];
}

export interface GateTiming {
  gate: GateId;
  executions: number;
  timed: number;
  untimed: number;
  outcomes: Record<string, number>;
  median_s: number | null;
  p95_s: number | null;
  mean_s: number | null;
  total_s: number;
}

export interface GateBenefit {
  gate: GateId;
  reached: number;
  unsafe_reached: number;
  unsafe_stopped: number;
  safe_stopped: number;
  tool_error_stopped: number;
  untimed: number;
  seconds: number;
  catches_per_gate_minute: number | null;
  cumulative_seconds: number;
  cumulative_unsafe_stopped: number;
  unsafe_escaping_after: number;
}

export interface ValidationCostData {
  schema_version: number;
  analysis: 'validation_cost';
  analysis_timestamp: string;
  generator: string;
  methods_doc: string;
  definitions: Record<string, string>;
  cohorts: Record<
    Cohort,
    {
      timing: GateTiming[];
      benefit: {
        cohort: Cohort;
        judged_patches: number;
        unsafe_patches: number;
        path_anomalies: number;
        gates: GateBenefit[];
      };
      conclusions: string[];
    }
  >;
  cross_reference: {
    source: string;
    on_disk_matches: boolean;
    on_disk_note: string;
    note: string;
    rows: Array<Record<string, string>>;
  };
  source_artifacts: SourceArtifact[];
}
