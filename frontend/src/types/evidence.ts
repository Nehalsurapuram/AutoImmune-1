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
}
