import type { PipelineStage, QueryRun } from "./types";

export const STAGE_LABELS: Record<PipelineStage, string> = {
  queued: "Waiting for the local model",
  requirements: "Clarifying your requirements",
  research: "Planning technology research",
  search: "Searching for the latest tech stack",
  evaluation: "Comparing the best-fit technologies",
  architecture: "Building your architecture",
  critique: "Reviewing the architecture",
  revision: "Refining the architecture",
  final_review: "Checking the revised architecture",
  saving: "Saving your complete design",
  needs_clarification: "Waiting for your answers",
  complete: "Design complete",
  failed: "Run needs attention",
};
export function isActive(run?: Pick<QueryRun, "status">) {
  return run?.status === "queued" || run?.status === "running";
}
export const CORE_STAGES: PipelineStage[] = [
  "requirements",
  "research",
  "search",
  "evaluation",
  "architecture",
  "critique",
];

export function timeline(run: QueryRun) {
  const visited = new Set(run.events.map((event) => event.stage));
  const stages = [...CORE_STAGES];
  if (visited.has("revision")) stages.push("revision");
  if (visited.has("final_review")) stages.push("final_review");
  stages.push("saving");
  return stages.map((stage) => ({
    stage,
    state:
      run.stage === stage ? "current" : visited.has(stage) ? "done" : "pending",
    at: run.events.find((event) => event.stage === stage)?.at,
  }));
}
