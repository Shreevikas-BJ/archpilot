"use client";

import { useState } from "react";
import type { ArchitectureResponse } from "@/lib/types";
import { Icon } from "./icon";
import { MermaidDiagram } from "./mermaid-diagram";

const TABS = ["Overview", "Decisions", "Delivery", "Sources"] as const;

export function ArchitectureResult({
  result,
}: {
  result: ArchitectureResponse;
}) {
  const [tab, setTab] = useState<(typeof TABS)[number]>("Overview");
  const plan = result.architecture;
  if (!plan) return null;
  const auditPrefix = "Responsibility audit - ";
  const audit = plan.tradeoffs.filter((item) => item.startsWith(auditPrefix));
  const tradeoffs = plan.tradeoffs.filter((item) => !item.startsWith(auditPrefix));

  function download() {
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(result, null, 2)], { type: "application/json" }),
    );
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "archpilot-" + result.run_id + ".json";
    anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  return (
    <section className="resultPanel panel" aria-label="Architecture result">
      <header className="resultIntro">
        <div className="sectionTop">
          <span className="eyebrow blue">YOUR ARCHITECTURE</span>
          <span className="savedBadge">
            <Icon name="check" /> Saved
          </span>
        </div>
        <h2>{plan.title}</h2>
        <p>{plan.summary}</p>
        <div className="resultMeta">
          <span>
            <Icon name="layers" />
            {plan.components.length} components
          </span>
          <span>
            <Icon name="link" />
            {result.research_sources.length} sources
          </span>
          <span
            className={result.critique?.approved ? "approved" : "reviewNeeded"}
          >
            {result.critique?.approved
              ? "Critic approved"
              : "Review recommended"}
          </span>
        </div>
        <button className="textButton exportButton" onClick={download}>
          <Icon name="download" /> Export this design
        </button>
      </header>
      <nav className="resultTabs" aria-label="Result sections">
        {TABS.map((name) => (
          <button
            key={name}
            className={tab === name ? "selected" : ""}
            aria-pressed={tab === name}
            onClick={() => setTab(name)}
          >
            {name}
            {name === "Sources" && (
              <span>{result.research_sources.length}</span>
            )}
          </button>
        ))}
      </nav>
      <div className="resultBody">
        {tab === "Overview" && (
          <>
            <div className="sectionTop">
              <h3>System map</h3>
              <span className="muted tiny">GENERATED FROM YOUR BRIEF</span>
            </div>
            {result.mermaid ? (
              <MermaidDiagram definition={result.mermaid} />
            ) : (
              <p>No diagram is available for this design.</p>
            )}
            <h3 className="spacedHeading">Building blocks</h3>
            <div className="componentGrid">
              {plan.components.map((component, index) => (
                <article className="componentCard" key={component.id}>
                  <span className="componentNumber">
                    {String(index + 1).padStart(2, "0")}
                  </span>
                  <h4>{component.name}</h4>
                  <div className="muted tiny">{component.category.replaceAll("_", " ")}</div>
                  <span className="technology">{component.technology}</span>
                  <p>{component.purpose}</p>
                  <div className="deployment">{component.deployment}</div>
                </article>
              ))}
            </div>
            <div className="costEstimate">
              <Icon name="layers" />
              <div>
                <span>Estimated monthly cost</span>
                <p>{plan.estimated_monthly_cost}</p>
              </div>
            </div>
          </>
        )}
        {tab === "Decisions" && (
          <>
            <h3>Why this stack</h3>
            <p className="muted">{result.evaluation?.industry_baseline}</p>
            {result.evaluation?.candidates.map((candidate) => (
              <article
                className="decisionCard"
                key={candidate.name + candidate.role}
              >
                <div className="sectionTop">
                  <h4>{candidate.name}</h4>
                  <span className="fitBadge">{candidate.fit} fit</span>
                </div>
                <span className="muted tiny">{candidate.role}</span>
                <p>{candidate.rationale}</p>
                <div className="prosCons">
                  <div>
                    <strong>Strengths</strong>
                    <ul>
                      {candidate.strengths.map((s) => (
                        <li key={s}>{s}</li>
                      ))}
                    </ul>
                  </div>
                  <div>
                    <strong>Considerations</strong>
                    <ul>
                      {candidate.weaknesses.map((s) => (
                        <li key={s}>{s}</li>
                      ))}
                    </ul>
                  </div>
                </div>
              </article>
            ))}
            <h3 className="spacedHeading">Tradeoffs</h3>
            <ul className="detailList">
              {tradeoffs.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
            {audit.length > 0 && (
              <>
                <h3 className="spacedHeading">Responsibility &amp; durability review</h3>
                <p className="muted">
                  Each component is checked for its assigned role and what happens to
                  acknowledged data if it disappears. These are the critic&apos;s findings.
                </p>
                <ul className="detailList">
                  {audit.map((item, index) => (
                    <li key={index}>{item.slice(auditPrefix.length)}</li>
                  ))}
                </ul>
              </>
            )}
            {result.critique && (
              <div className="reviewCard">
                <h3>Independent critique</h3>
                <p>
                  {result.critique.approved
                    ? "Approved by the critic agent."
                    : "The critic recommends reviewing the points below."}{" "}
                  Confidence: {Math.round(result.critique.confidence * 100)}%.
                </p>
                <ul>
                  {[
                    ...result.critique.risks,
                    ...result.critique.required_changes,
                    ...result.critique.unnecessary_components,
                  ].map((item, index) => (
                    <li key={index}>{item}</li>
                  ))}
                </ul>
              </div>
            )}
          </>
        )}
        {tab === "Delivery" && (
          <>
            <h3>From plan to implementation</h3>
            <ol className="deliverySteps">
              {plan.implementation_steps.map((step, index) => (
                <li key={step}>
                  <span>{String(index + 1).padStart(2, "0")}</span>
                  <p>{step}</p>
                </li>
              ))}
            </ol>
            <h3 className="spacedHeading">Design assumptions</h3>
            <ul className="detailList">
              {plan.assumptions.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </>
        )}
        {tab === "Sources" && (
          <>
            <h3>Research behind the design</h3>
            <p className="muted">
              Review the original sources used during research.
            </p>
            <div className="sources">
              {result.research_sources.map((source, index) => (
                <a
                  href={source.url}
                  target="_blank"
                  rel="noreferrer"
                  key={source.url + index}
                >
                  <span className="sourceNumber">
                    {String(index + 1).padStart(2, "0")}
                  </span>
                  <div>
                    <strong>{source.title}</strong>
                    <span>{source.url}</span>
                    <p>{source.snippet}</p>
                  </div>
                  <Icon name="arrow" />
                </a>
              ))}
            </div>
          </>
        )}
      </div>
      <footer className="resultFooter">
        Run <code>{result.run_id}</code>
      </footer>
    </section>
  );
}
