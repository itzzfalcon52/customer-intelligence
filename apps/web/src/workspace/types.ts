export interface Dataset {
  id: string;
  original_filename: string;
  row_count: number;
  column_count: number;
}
export interface Column {
  name: string;
  inferred_type: 'numeric' | 'string' | 'empty';
  missing_count: number;
  missing_percentage: number;
  unique_count: number;
  numeric_summary: null | {
    minimum: number | null;
    maximum: number | null;
    mean: number | null;
    median: number | null;
  };
}
export interface Profile {
  dataset_id: string;
  original_filename: string;
  row_count: number;
  column_count: number;
  duplicate_row_count: number;
  columns: Column[];
  preview: Record<string, string | null>[];
  warnings: string[];
}
export interface Task {
  id: string;
  dataset_id: string;
  target_column: string;
  positive_label: string;
  id_column: string | null;
  feature_columns: string[];
  features_available_at_prediction: true;
  label_mapping: Record<string, number>;
  evaluation_strategy: string;
  time_column?: string | null;
  random_seed: number;
  dataset_sha256: string;
}
export type TaskInput = Pick<
  Task,
  | 'target_column'
  | 'positive_label'
  | 'id_column'
  | 'feature_columns'
  | 'features_available_at_prediction'
  | 'time_column'
>;
export interface TargetCheck {
  target_valid: boolean;
  class_counts: Record<string, number>;
  blockers: string[];
  missing_label_count: number;
  distinct_class_count: number;
  class_counts_truncated: boolean;
}
export interface Job {
  id: string;
  kind: string;
  state: 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled';
  stage: string;
  error: string | null;
  result_id: string | null;
  created_at: string;
  heartbeat_at: string | null;
  cancel_requested: boolean;
}
export interface Metrics {
  row_count: number;
  positive_count: number;
  predicted_positive_count: number;
  accuracy: number;
  precision: number | null;
  recall: number;
  f1: number;
  roc_auc: number;
  average_precision: number;
  true_negative: number;
  false_positive: number;
  false_negative: number;
  true_positive: number;
}
export interface Candidate {
  training_cv_average_precision?: number | null;
  training_cv_std?: number | null;
  model_name: string;
  candidate_id: string;
  parameters: Record<string, string | number>;
  validation: Metrics;
  warnings: string[];
  elapsed_seconds: number;
}
export interface Report {
  training_cv_folds?: number;
  threshold_policy?: string;
  threshold_selection?: {
    source?: string;
    validation_curve?: (Metrics & { threshold: number })[];
  };
  executive_briefing?: { paragraphs: string[] };
  task_id: string;
  dataset_id: string;
  target_column: string;
  positive_label: string;
  feature_columns: string[];
  classification_threshold: number;
  results: Candidate[];
  failures: { candidate_id: string; error: string }[];
  best_validation_model: string;
  best_validation_candidate_id: string | null;
  selection_warning: string | null;
  selection_metric: string;
  random_seed: number;
  dataset_sha256: string;
}
export interface Run {
  run_id: string;
  created_at: string;
  report: Report;
  calibration: Record<string, unknown> | null;
}
export interface RunSummary {
  run_id: string;
  created_at: string;
  task_id: string;
  model: string;
  average_precision: number;
  test_evaluated: boolean;
  error?: string;
}
export interface Contact {
  k: number;
  precision: number;
  recall: number;
  lift: number;
  true_positive: number;
}
export interface Evaluation {
  metrics: Metrics;
  contact_metrics: Contact[];
  warning: string;
  calibration_checks: Record<string, unknown>;
}
export interface Score {
  id: string;
  run_id: string;
  dataset_id: string;
  row_count: number;
  contact_count: number;
  ranking: string;
  value_column: string | null;
  value_unit: string | null;
  warnings: string[];
  created_at: string;
  holdout_count?: number;
  holdout_rate?: number;
}
export interface Customer {
  customer_id: string;
  row_reference: number;
  risk_score: number;
  rank: number;
  customer_value: number | null;
  exposure_proxy: number | null;
  priority_rank: number | null;
  group?: 'contact' | 'holdout' | null;
}
export interface CustomerPage {
  total: number;
  offset: number;
  customers: Customer[];
}
export interface Analysis {
  kind?: string;
  id: string;
  run_id?: string;
  task_id?: string;
  score_id?: string;
  partition?: string;
  warning?: string;
  importance_warning?: string;
  permutation_importance?: {
    feature: string;
    mean_ap_decrease: number;
    std: number;
  }[];
  contact_curve?: Contact[];
  calibration?: {
    brier_score: number;
    bins: {
      lower: number;
      mean_score: number | null;
      observed_positive_rate: number | null;
      count: number;
    }[];
  };
  segments?: {
    segment: string;
    row_count: number;
    metrics?: Metrics;
    warning?: string;
  }[];
  effects?: {
    feature: string;
    reference_value: string;
    risk_score_change_if_replaced: number;
  }[];
  results?: Record<string, Metrics>;
  heuristic?: {
    column: string;
    direction: string;
    average_precision: number;
    warning: string;
  };
}
export interface Message {
  conversation_id: string;
  turn_id: string;
  answer: string;
  model: string;
  events: {
    tool: string;
    resource_id: string | null;
    evidence_path: string | null;
  }[];
  model_call_count: number;
  trace_id?: string | null;
  verification?: {
    grounded: boolean;
    numbers_checked: number;
    ungrounded: string[];
    causal_claims?: string[];
    revised: boolean;
  } | null;
}
export interface AgentTrace {
  id: string;
  kind: string;
  status: string;
  error_code: string | null;
  prompt_version: string | null;
  model_calls: number;
  tool_calls: number;
  retries: number;
  input_tokens: number | null;
  output_tokens: number | null;
  cost_usd: number | null;
  duration_ms: number;
  created_at: string;
}
export interface AgentSpan {
  id: string;
  sequence: number;
  kind: 'model' | 'tool';
  name: string;
  status: string;
  parent: string | null;
  model: string | null;
  attempts: number;
  input_tokens: number | null;
  output_tokens: number | null;
  duration_ms: number;
  error_code: string | null;
  evidence_path: string | null;
}
export interface TraceDetail {
  trace: AgentTrace;
  spans: AgentSpan[];
}
export interface Conversation {
  conversation_id: string;
  dataset_id: string;
  turns: { question: string; response: Message; created_at: string }[];
}
export interface Plan {
  candidates: {
    model: string;
    candidate_id: string;
    parameters: Record<string, unknown>;
  }[];
  selection_metric: string;
  limitations: string[];
}
export interface Split {
  train: { row_count: number; class_counts: Record<string, number> };
  validation: { row_count: number; class_counts: Record<string, number> };
  test: { row_count: number; class_counts: Record<string, number> };
}
export interface EvidenceItem {
  tool: string;
  hypothesis?: string;
  arguments: Record<string, unknown>;
  result?: Record<string, unknown>;
  error?: string;
}
export interface InvestigationFinding {
  statement: string;
  kind: string;
  evidence: string[];
}
export interface Investigation {
  id: string;
  kind: 'investigation';
  created_at: string;
  run_id: string;
  task_id: string;
  question: string;
  partition: string;
  evidence: Record<string, EvidenceItem>;
  report: {
    headline: string;
    findings: InvestigationFinding[];
    caveats: string[];
    next_steps: string[];
    withheld: { statement: string; problems: string[] }[];
    status: 'verified' | 'partial' | 'unverified';
  };
  trace_id: string;
  model_calls: number;
  warning: string;
}
export interface Memory {
  assumptions: Partial<{
    budget: number;
    contact_cost: number;
    offer_cost: number;
    assumed_save_rate: number;
    retained_value: number;
    currency: string;
  }>;
  assumptions_source: string | null;
  decisions: { text: string }[];
  updated_at: string | null;
}
export interface PendingAction {
  id: string;
  kind: string;
  summary: string;
  payload: Record<string, unknown>;
  status: 'pending' | 'approved' | 'rejected';
  origin: string;
  trace_id: string | null;
  result_id: string | null;
  created_at: string;
  decided_at: string | null;
}
