/* ─── WebSocket event types & shared interfaces ─── */

// Pipeline stages
export type PipelineStage =
  | "PLANNING"
  | "CODING"
  | "TESTING"
  | "REVIEWING"
  | "VALIDATING"
  | "COMPLETE";

export type StageStatus = "pending" | "in_progress" | "complete" | "error" | "bypassed";

export type CheckpointType = "PLANNING_REVIEW" | "CODE_REVIEW" | "TEST_REVIEW" | "FINAL_REVIEW";

export type SessionStatus =
  | "pending"
  | "running"
  | "checkpoint"
  | "complete"
  | "error";

// ─── Planning Agent types ─────────────────────────────────────

export type PlanningModuleId =
  | "project_understanding"
  | "functional_requirements"
  | "folder_structure"
  | "architecture_design"
  | "component_breakdown"
  | "dependency_planning"
  | "data_flow"
  | "file_responsibilities"
  | "api_planning"
  | "database_planning"
  | "security_considerations"
  | "testing_strategy"
  | "code_standards"
  | "risks_challenges"
  | "execution_roadmap";

export interface PlanningModuleMeta {
  id: PlanningModuleId;
  label: string;
  description: string;
  icon: string;
}

export interface PlanningConfig {
  modules: Record<string, boolean>;
}

export interface PlanningDocument {
  project_understanding?: Record<string, unknown> | null;
  functional_requirements?: Record<string, unknown> | null;
  folder_structure?: { tree?: string; notes?: string } | null;
  architecture_design?: Record<string, unknown> | null;
  component_breakdown?: Record<string, unknown> | null;
  dependency_planning?: Record<string, unknown> | null;
  data_flow?: Record<string, unknown> | null;
  file_responsibilities?: Record<string, unknown> | null;
  api_planning?: Record<string, unknown> | null;
  database_planning?: Record<string, unknown> | null;
  security_considerations?: Record<string, unknown> | null;
  testing_strategy?: Record<string, unknown> | null;
  code_standards?: Record<string, unknown> | null;
  risks_challenges?: Record<string, unknown> | null;
  execution_roadmap?: Record<string, unknown> | null;
  generated_at?: number;
  requirements?: string;
}

export interface PlanningReviewData {
  plan: PlanningDocument;
  modules_selected: Record<string, boolean>;
  modules_generated: string[];
  plan_markdown: string;
}

// ─── WebSocket Events ───────────────────────────────

export interface WSEvent<T = unknown> {
  type: string;
  data: T;
}

export interface StageUpdateData {
  stage: PipelineStage;
  status: StageStatus;
  message: string;
}

export interface FileCreatedData {
  path: string;
  content: string;
  language: string;
}

export interface TestResultsData {
  passed: boolean;
  /** True when the majority (>=70%) of tests passed even if some failed. */
  majority_passed?: boolean;
  /** Pass rate as a fraction in [0, 1]. */
  pass_rate?: number;
  output: string;
  coverage_line: number;
  coverage_branch: number;
  duration: number;
  execution_mode?: string;
  report_data?: Record<string, any>;
  rca_data?: Record<string, any>;
}

export interface ReviewReportData {
  issues: string[];
  pylint_score: number;
  security_issues: number;
}

export interface CheckpointData {
  checkpoint_type: CheckpointType;
  message: string;
  data: Record<string, unknown>;
}

export interface MetricsData {
  total_time: number;
  attempts: number;
  coverage: number;
  pylint_score: number;
  files_count: number;
  llm_cost: string;
}

export interface PipelineCompleteData {
  status: "success" | "error" | "max_retries";
  message?: string;
  files?: string[];
  metrics?: Record<string, unknown>;
}

export interface LogData {
  message: string;
}

// ─── UI Models ──────────────────────────────────────

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  timestamp: number;
}

export interface FileNode {
  name: string;
  path: string;
  isDirectory: boolean;
  children: FileNode[];
  content?: string;
  language?: string;
}

export interface TimelineStep {
  stage: PipelineStage;
  status: StageStatus;
  message: string;
  timestamp: number;
}
