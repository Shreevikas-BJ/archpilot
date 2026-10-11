"use client";

import Image from "next/image";
import { useRef } from "react";
import type { ArchitectureMode, RuntimeMetadata } from "@/lib/types";
import { useDesignWorkspace } from "@/lib/use-design-workspace";
import { STAGE_LABELS } from "@/lib/progress";
import { ArchitectureResult } from "./architecture-result";
import { QueryProgress } from "./query-progress";
import { QueryRecord } from "./query-record";
import { Icon } from "./icon";

const MODES: { value: ArchitectureMode; label: string; description: string }[] =
  [
    {
      value: "cost_effective",
      label: "Cost effective",
      description: "A lean stack. Lower running costs.",
    },
    {
      value: "balanced",
      label: "Balanced",
      description: "Practical tradeoffs for everyday scale.",
    },
    {
      value: "high_performance",
      label: "High performance",
      description: "Prioritize speed and room to grow.",
    },
  ];

const DEMO_BRIEF =
  "Build a tiny internal read-only staff directory for five employees on our existing VPN. FastAPI serves HTML and PostgreSQL stores 100 names and work phone numbers. An admin imports CSV monthly. No public access, login UI, integrations, attachments or regulated data. Deploy two containers on our existing Linux host; our VPN and daily host backups handle access control and recovery. Budget: zero incremental hosting cost. One developer, one week. Business-hours availability, one-second latency, 24-hour RPO and one-day RTO. Assume remaining details; no clarification is needed. Keep the design to two or three components, compare three relevant technologies, and use three focused research queries on official FastAPI and PostgreSQL documentation.";

function EmptyResult({ runtime }: { runtime: RuntimeMetadata | null }) {
  return (
    <section className="panel emptyResult">
      <div className="emptyHeader">
        <span className="eyebrow">YOUR NEXT SYSTEM STARTS HERE</span>
        <span className="draftBadge">Ready for a brief</span>
      </div>
      <div className="blueprint" aria-hidden="true">
        <div className="blueprintNode">
          <Icon name="grid" />
          <span>Application</span>
        </div>
        <span className="blueprintLine" />
        <div className="blueprintNode centerNode">
          <Icon name="layers" />
          <span>Services</span>
        </div>
        <span className="blueprintLine" />
        <div className="blueprintNode">
          <Icon name="file" />
          <span>Data</span>
        </div>
      </div>
      <span className="previewCaption">ILLUSTRATIVE SYSTEM MAP</span>
      <h2>
        Turn the big idea
        <br />
        into a buildable plan.
      </h2>
      <p>
        Describe what you need. This workspace connects the requirements,
        research, and tradeoffs into a clear architecture.
      </p>
      <div className="featureList">
        <div>
          <Icon name="layers" />
          <span>
            <strong>A system you can see</strong>
            <small>Components, connections, and deployment choices.</small>
          </span>
        </div>
        <div>
          <Icon name="link" />
          <span>
            <strong>Decisions with evidence</strong>
            <small>Technology comparisons linked to research.</small>
          </span>
        </div>
        <div>
          <Icon name="check" />
          <span>
            <strong>A practical next step</strong>
            <small>A reviewed plan with implementation steps.</small>
          </span>
        </div>
      </div>
      <div className="emptyFooter">
        <span className="statusDot" />
        {runtime?.mode === "local"
          ? "Local inference"
          : runtime?.label || "Private compute"}
        . Real research. Saved designs.
      </div>
    </section>
  );
}

export function ArchitectureStudio() {
  const {
    problem,
    changeProblem,
    mode,
    setMode,
    clarifications,
    setClarifications,
    query,
    queries,
    latest,
    selected,
    setSelectedRunId,
    connected,
    runtime,
    historyError,
    loading,
    submitting,
    opening,
    busy,
    error,
    pollError,
    refreshHistory,
    openQuery,
    newDesign,
    useDemo,
    submit,
  } = useDesignWorkspace();
  const problemInput = useRef<HTMLTextAreaElement>(null);
  const questions =
    latest?.status === "needs_clarification"
      ? (latest.response?.clarifying_questions ?? [])
      : [];
  const result = selected?.response;

  return (
    <div className="appShell">
      <a className="skipLink" href="#workspace">
        Skip to workspace
      </a>
      <aside className="sidebar" aria-label="Query navigation">
        <a className="brand brandImage" href="/" aria-label="Home">
          <Image
            src="/archpilot-logo.png"
            alt="ArchPilot"
            width={1774}
            height={887}
            sizes="(max-width: 640px) 176px, 210px"
            priority
          />
        </a>
        <div className="workspaceLabel">YOUR WORKSPACE</div>
        <div className="activeNav">
          <Icon name="grid" /> Architecture studio
        </div>
        <button
          className="newDesignButton"
          onClick={() => {
            newDesign();
            problemInput.current?.focus();
          }}
          disabled={submitting || opening}
        >
          <Icon name="plus" /> New query
        </button>
        <div className="historyHeading">
          <span>SAVED QUERIES</span>
          <button
            className="iconButton"
            aria-label="Refresh saved queries"
            onClick={() => void refreshHistory()}
          >
            <Icon name="refresh" />
          </button>
        </div>
        <div className="historyList">
          {queries.map((item) => (
            <div className="historyQuery" key={item.query_id}>
              <button
                className={
                  "historyItem " +
                  (query?.query_id === item.query_id ? "current" : "")
                }
                disabled={submitting || opening}
                onClick={() => void openQuery(item.query_id)}
                title={item.problem}
              >
                <Icon name="file" />
                <span>
                  <strong>{item.title}</strong>
                  <small>
                    {item.status === "complete"
                      ? "Design saved"
                      : item.status === "running" || item.status === "queued"
                        ? STAGE_LABELS[item.stage]
                        : item.status === "needs_clarification"
                          ? "Needs your answers"
                          : "Needs attention"}
                  </small>
                  <small>
                    {item.run_count} {item.run_count === 1 ? "round" : "rounds"}{" "}
                    ·{" "}
                    {new Date(item.updated_at).toLocaleDateString(undefined, {
                      month: "short",
                      day: "numeric",
                    })}
                  </small>
                </span>
              </button>
              {query?.query_id === item.query_id && (
                <div className="queryTree">
                  <span>Requirements & complete designs</span>
                  {query.runs.map((run, index) => (
                    <button
                      key={run.run_id}
                      className={
                        selected?.run_id === run.run_id ? "selected" : ""
                      }
                      onClick={() => setSelectedRunId(run.run_id)}
                    >
                      Round {index + 1}
                      <span>
                        {run.status === "complete"
                          ? "Design"
                          : run.status === "needs_clarification"
                            ? "Clarification"
                            : run.status === "failed"
                              ? "Failed"
                              : "In progress"}
                      </span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          ))}
          {!queries.length && !historyError && (
            <p className="historyEmpty">
              Each query keeps its classifications, answers, and complete
              designs here.
            </p>
          )}
          {historyError && (
            <p className="historyEmpty" role="status">
              Saved queries are unavailable. Check the backend and database
              connection.
            </p>
          )}
        </div>
        <div className="sidebarFooter">
          <span className="localIcon">
            <Icon name="spark" />
          </span>
          <div>
            <strong>{runtime?.label ?? "Your compute"}</strong>
            <span>{runtime?.llm ?? "Configured model endpoint"}</span>
          </div>
          <span className="localBadge">
            {runtime?.mode === "cloud"
              ? "CLOUD"
              : runtime?.mode === "self_hosted"
                ? "PRIVATE"
                : "LOCAL"}
          </span>
        </div>
      </aside>
      <main className="mainContent" id="workspace" tabIndex={-1}>
        <div className="topbar">
          <div>
            Workspace <span>/</span> <strong>Architecture studio</strong>
          </div>
          <span
            className={
              "connectionBadge " + (connected === false ? "offline" : "")
            }
          >
            <span
              className={"statusDot " + (connected === null ? "checking" : "")}
            />
            {connected === null
              ? "Checking connection"
              : connected
                ? runtime
                  ? `Connected · ${runtime.label}`
                  : "Backend & database connected"
                : "Backend unavailable"}
          </span>
        </div>
        <header className="hero">
          <div>
            <p className="eyebrow blue">FROM IDEA TO IMPLEMENTATION</p>
            <h1>Build with a clear plan.</h1>
            <p>Make confident architecture decisions, grounded in research.</p>
          </div>
          <span className="studioBadge">
            <Icon name="spark" /> Architecture studio
          </span>
        </header>
        <div className="workspaceGrid">
          <form onSubmit={submit} className="panel briefPanel">
            <div className="sectionTitle">
              <span className="stepNumber">01</span>
              <div>
                <h2>{query ? "Your original brief" : "Define your brief"}</h2>
                <p>
                  {query
                    ? "Answers and versions stay in this query."
                    : "Start with the problem, not the stack."}
                </p>
              </div>
            </div>
            <div className="inputHeading">
              <label htmlFor="problem">What are you building?</label>
              <button
                className="textButton"
                type="button"
                disabled={submitting || opening}
                onClick={() => useDemo(DEMO_BRIEF)}
              >
                Use demo brief <Icon name="arrow" />
              </button>
            </div>
            <textarea
              ref={problemInput}
              id="problem"
              name="problem"
              required
              minLength={20}
              maxLength={8000}
              disabled={busy}
              value={problem}
              onChange={(event) => changeProblem(event.target.value)}
              placeholder="Describe your product, who it serves, and what success looks like. Include scale, budget, constraints, and existing systems."
              rows={9}
            />
            <div className="inputHint">
              <span>
                {query
                  ? "Editing this brief starts a new query."
                  : "A little context makes a better design."}
              </span>
              <span>{problem.length.toLocaleString()} / 8,000</span>
            </div>
            <fieldset className="modeFieldset" disabled={busy}>
              <legend>What matters most?</legend>
              <div className="modeOptions">
                {MODES.map((item) => (
                  <label
                    key={item.value}
                    className={
                      "modeOption " + (mode === item.value ? "chosen" : "")
                    }
                  >
                    <input
                      type="radio"
                      name="mode"
                      value={item.value}
                      checked={mode === item.value}
                      onChange={() => setMode(item.value)}
                    />
                    <span>
                      <strong>{item.label}</strong>
                      <small>{item.description}</small>
                    </span>
                    {mode === item.value && <Icon name="check" />}
                  </label>
                ))}
              </div>
            </fieldset>
            {questions.length > 0 && (
              <div className="clarifications">
                <h3>A few details to refine</h3>
                <p>
                  These answers will be saved as the next round inside this
                  query.
                </p>
                {questions.map((question) => (
                  <label key={question}>
                    {question}
                    <input
                      required
                      disabled={busy}
                      value={clarifications[question] ?? ""}
                      onChange={(event) =>
                        setClarifications((current) => ({
                          ...current,
                          [question]: event.target.value,
                        }))
                      }
                    />
                  </label>
                ))}
              </div>
            )}
            {error && (
              <p className="errorText" role="alert">
                {error}
              </p>
            )}
            <button
              className="primaryButton"
              disabled={
                busy || problem.trim().length < 20 || connected === false
              }
            >
              <Icon name="spark" />
              {submitting
                ? "Saving your query…"
                : opening
                  ? "Opening query…"
                  : loading
                    ? "Design in progress…"
                    : questions.length
                      ? "Save answers & continue"
                      : latest?.status === "failed"
                        ? "Retry in this query"
                        : query
                          ? "Create another design"
                          : "Design architecture"}
              {!busy && <Icon name="arrow" />}
            </button>
            <p className="formFootnote">
              <Icon name="clock" /> Progress and results are saved
              automatically.
            </p>
          </form>
          <div className="outputColumn queryOutput">
            {loading && latest && (
              <QueryProgress run={latest} reconnecting={pollError} />
            )}
            {query && (
              <QueryRecord
                query={query}
                selected={selected}
                onSelect={setSelectedRunId}
              />
            )}
            {result?.status === "complete" && result.architecture && (
              <ArchitectureResult key={result.run_id} result={result} />
            )}
            {!loading && latest?.status === "needs_clarification" && (
              <section className="panel clarificationPanel">
                <Icon name="file" />
                <span className="eyebrow blue">LET’S FILL IN THE GAPS</span>
                <h2>A clearer brief. A stronger design.</h2>
                <p>
                  Your requirements have been classified and saved above. Add
                  the requested answers in your brief to continue.
                </p>
              </section>
            )}
            {!query && !opening && <EmptyResult runtime={runtime} />}
            {opening && !query && (
              <section className="panel clarificationPanel">
                <p role="status">Opening your saved query…</p>
              </section>
            )}
          </div>
        </div>
        <footer className="workspaceFooter">
          Thoughtful architecture, from first question to final plan.
        </footer>
      </main>
    </div>
  );
}
