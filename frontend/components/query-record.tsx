"use client";

import type { DesignQuery, QueryRun, RequirementsAnalysis } from "@/lib/types";
import { STAGE_LABELS } from "@/lib/progress";
import { Icon } from "./icon";

const CLASSIFICATIONS: { key: keyof RequirementsAnalysis; label: string }[] = [
  { key: "problem_summary", label: "Problem definition" },
  { key: "business_goal", label: "Business goal" },
  { key: "users_and_scale", label: "Users & scale" },
  { key: "latency_expectation", label: "Performance & latency" },
  { key: "data_characteristics", label: "Data requirements" },
  { key: "security_and_compliance", label: "Security & compliance" },
  { key: "existing_stack", label: "Existing technology" },
  { key: "hard_constraints", label: "Hard constraints" },
  { key: "assumptions", label: "Assumptions" },
  { key: "clarifying_questions", label: "Questions identified" },
];

export function QueryRecord({
  query,
  selected,
  onSelect,
}: {
  query: DesignQuery;
  selected?: QueryRun;
  onSelect: (runId: string) => void;
}) {
  function download() {
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(query, null, 2)], { type: "application/json" }),
    );
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "query-" + query.query_id + ".json";
    anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  const answers = Object.entries(selected?.request.clarifications ?? {});
  return (
    <section
      className="panel queryRecord"
      aria-label="Saved query and requirements"
    >
      <div className="sectionTop">
        <span className="eyebrow blue">YOUR SAVED QUERY</span>
        <span className="savedBadge">
          <Icon name="check" /> Saved to database
        </span>
      </div>
      <h2>{query.title}</h2>
      <p className="queryHint">
        One original brief. Every classification, clarification, and design
        version kept together.
      </p>
      <details className="originalQuery">
        <summary>Original user query</summary>
        <p>{query.problem}</p>
      </details>
      <div className="queryRounds" aria-label="Saved rounds">
        {query.runs.map((run, index) => (
          <button
            key={run.run_id}
            aria-pressed={selected?.run_id === run.run_id}
            className={selected?.run_id === run.run_id ? "selected" : ""}
            onClick={() => onSelect(run.run_id)}
          >
            <span>Round {index + 1}</span>
            <small>
              {run.status === "complete"
                ? "Complete design"
                : run.status === "needs_clarification"
                  ? "Clarifications"
                  : run.status === "failed"
                    ? "Needs attention"
                    : STAGE_LABELS[run.stage]}
            </small>
          </button>
        ))}
      </div>
      {selected?.requirements ? (
        <details className="classifiedRequirements">
          <summary>
            <span>
              <Icon name="layers" /> Classified requirements
            </span>
            <small>
              {CLASSIFICATIONS.length} categories · Round{" "}
              {query.runs.indexOf(selected) + 1}
            </small>
          </summary>
          <dl className="requirementGrid">
            {CLASSIFICATIONS.map(({ key, label }) => {
              const value = selected.requirements![key];
              return (
                <div key={key}>
                  <dt>{label}</dt>
                  <dd>
                    {Array.isArray(value) ? (
                      value.length ? (
                        <ul>
                          {value.map((item, index) => (
                            <li key={index}>{item}</li>
                          ))}
                        </ul>
                      ) : (
                        <span className="muted">None identified</span>
                      )
                    ) : (
                      value
                    )}
                  </dd>
                </div>
              );
            })}
          </dl>
        </details>
      ) : (
        <p className="classificationPending">
          Requirement classifications will appear here as soon as analysis
          finishes.
        </p>
      )}
      {answers.length > 0 && (
        <details className="clarificationAnswers">
          <summary>
            Clarification answers <small>{answers.length} saved</small>
          </summary>
          <dl>
            {answers.map(([question, answer]) => (
              <div key={question}>
                <dt>{question}</dt>
                <dd>{answer}</dd>
              </div>
            ))}
          </dl>
        </details>
      )}
      {selected?.error && (
        <p className="errorText" role="alert">
          {selected.error} Your earlier classifications and designs remain saved
          under this query.
        </p>
      )}
      <div className="queryRecordFooter">
        <button className="textButton" onClick={download}>
          <Icon name="download" /> Export entire query
        </button>
        <span>
          {query.runs.length} {query.runs.length === 1 ? "round" : "rounds"} ·{" "}
          {query.runs.filter((run) => run.status === "complete").length}{" "}
          complete designs
        </span>
      </div>
    </section>
  );
}
