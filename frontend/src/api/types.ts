import type { Unit } from "../lib/format";

export interface Page<T> {
  items: T[];
}

export interface Dataset {
  id: string;
  name: string;
  domain: string;
  kind: string;
  published_run_id: string | null;
  rerun_requested_at: string | null;
  created_at: string;
}

export interface Ingestion {
  id: string;
  original_name: string;
  sha256: string;
  size_bytes: number;
  row_count: number | null;
  status: string;
  is_active: boolean;
  created_at: string;
}

export interface RunRequest {
  run_id: string | null;
  rerun_queued: boolean;
}

export interface Upload extends RunRequest {
  ingestion: Ingestion;
  created: boolean;
}

export type RunStatus = "queued" | "running" | "succeeded" | "failed" | "blocked_by_quality";

export interface Stage {
  stage: string;
  status: string;
  rows_in: number | null;
  rows_out: number | null;
  rows_quarantined: number | null;
  duration_ms: number | null;
}

export interface Run {
  id: string;
  data_source_id: string;
  trigger: string;
  status: RunStatus;
  error_code: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  stages: Stage[];
}

export interface QualityResult {
  rule_id: string;
  stage: string;
  severity: "blocking" | "warning";
  passed: boolean;
  observed: number | null;
  threshold: number | null;
  description: string;
}

export interface Kpi {
  name: string;
  label: string;
  unit: Unit;
  description: string;
  value: number | null;
  previous: number | null;
  change: number | null;
}

export interface Ranked {
  key: string;
  label: string | null;
  value: number | null;
}

export interface Dashboard {
  range: { from: string; to: string; min: string; max: string; default_limited?: boolean };
  kpis: Kpi[];
  trend: { metric: string; grain: "day" | "month"; points: { period: string; value: number | null }[] };
  top_products: Ranked[];
  countries: Ranked[];
  freshness: {
    run_id: string | null;
    finished_at: string | null;
    quality: { passed: number; warnings: number; failed: number };
  };
}

export interface MetricAnswer {
  metric: string;
  label: string;
  description: string;
  unit: Unit;
  value: number | null;
  from: string;
  to: string;
  run_id: string;
  sql: string[];
  parameters: { start: string; end: string };
}

export interface SearchDocument {
  id: string;
  title: string;
}

export interface DocumentCitation {
  document_id: string;
  title: string;
  start_line: number;
  end_line: number;
  excerpt: string;
}

export interface SalesForecast {
  metric: string;
  unit: Unit;
  published_run_id: string;
  history_from: string;
  as_of: string;
  points: { date: string; seasonal_naive: number; weekday_average: number }[];
  backtest: {
    folds: number;
    days_evaluated: number;
    seasonal_naive_mae: number;
    weekday_average_mae: number;
  };
}
