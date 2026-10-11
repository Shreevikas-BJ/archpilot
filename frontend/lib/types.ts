export type ArchitectureMode =
  "cost_effective" | "balanced" | "high_performance";

export interface RuntimeMetadata {
  mode: "local" | "self_hosted" | "cloud";
  label: string;
  llm: string;
}

export interface RequirementsAnalysis {
  problem_summary: string;
  business_goal: string;
  users_and_scale: string;
  latency_expectation: string;
  data_characteristics: string;
  security_and_compliance: string;
  existing_stack: string[];
  hard_constraints: string[];
  assumptions: string[];
  clarifying_questions: string[];
}

export interface SearchSource {
  title: string;
  url: string;
  snippet: string;
  engine?: string | null;
  query: string;
}

export interface ToolEvaluation {
  name: string;
  role: string;
  maturity: "emerging" | "growing" | "established";
  cost_profile: string;
  performance_profile: string;
  operational_complexity: "low" | "medium" | "high";
  scalability: string;
  strengths: string[];
  weaknesses: string[];
  evidence_urls: string[];
  fit: "poor" | "conditional" | "good" | "excellent";
  rationale: string;
}

export interface EvaluationReport {
  industry_baseline: string;
  candidates: ToolEvaluation[];
  key_tradeoffs: string[];
  avoid_list: string[];
}

export interface ArchitectureComponent {
  id: string;
  name: string;
  technology: string;
  category: string;
  purpose: string;
  deployment: string;
}

export interface ArchitecturePlan {
  title: string;
  mode: ArchitectureMode;
  summary: string;
  components: ArchitectureComponent[];
  connections: { source: string; target: string; label: string }[];
  estimated_monthly_cost: string;
  assumptions: string[];
  tradeoffs: string[];
  implementation_steps: string[];
  source_urls: string[];
}

export interface Critique {
  approved: boolean;
  confidence: number;
  risks: string[];
  required_changes: string[];
  unnecessary_components: string[];
}

export interface ArchitectureResponse {
  run_id: string;
  status: "needs_clarification" | "complete";
  requirements: RequirementsAnalysis;
  clarifying_questions: string[];
  research_sources: SearchSource[];
  evaluation?: EvaluationReport | null;
  architecture?: ArchitecturePlan | null;
  critique?: Critique | null;
  mermaid?: string | null;
}

export interface ArchitectureRunSummary {
  run_id: string;
  title: string;
  mode: ArchitectureMode;
  status: "needs_clarification" | "complete";
  created_at: string;
}

export interface SavedArchitectureRun {
  request: {
    problem: string;
    mode: ArchitectureMode;
    clarifications: Record<string, string>;
  };
  response: ArchitectureResponse;
  created_at: string;
}

export type PipelineStage =
  | "queued"
  | "requirements"
  | "research"
  | "search"
  | "evaluation"
  | "architecture"
  | "critique"
  | "revision"
  | "final_review"
  | "saving"
  | "needs_clarification"
  | "complete"
  | "failed";
export type RunStatus =
  "queued" | "running" | "needs_clarification" | "complete" | "failed";
export interface QueryRun {
  run_id: string;
  request: {
    problem: string;
    mode: ArchitectureMode;
    clarifications: Record<string, string>;
  };
  status: RunStatus;
  stage: PipelineStage;
  requirements: RequirementsAnalysis | null;
  response: ArchitectureResponse | null;
  events: { stage: PipelineStage; at: string }[];
  error: string | null;
  created_at: string;
  updated_at: string;
}
export interface QuerySummary {
  query_id: string;
  title: string;
  problem: string;
  status: RunStatus;
  stage: PipelineStage;
  run_count: number;
  created_at: string;
  updated_at: string;
}
export interface DesignQuery {
  query_id: string;
  title: string;
  problem: string;
  runs: QueryRun[];
  created_at: string;
  updated_at: string;
}
