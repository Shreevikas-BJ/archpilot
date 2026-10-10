"use client";

import { useEffect, useState } from "react";
import { STAGE_LABELS, timeline } from "@/lib/progress";
import type { QueryRun } from "@/lib/types";
import { Icon } from "./icon";

export function QueryProgress({
  run,
  reconnecting,
}: {
  run: QueryRun;
  reconnecting: boolean;
}) {
  const [now, setNow] = useState(Date.now);
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  const elapsed = Math.max(
    0,
    Math.floor((now - new Date(run.created_at).getTime()) / 1000),
  );
  const current = run.events.at(-1);
  return (
    <section
      className="panel liveProgress"
      aria-label="Live generation progress"
    >
      <div className="progressHeadline">
        <span className="progressSymbol">
          <Icon name="spark" />
        </span>
        <div>
          <span className="eyebrow blue">
            {reconnecting ? "RECONNECTING" : "LIVE PROGRESS"}
          </span>
          <h2 role="status" aria-live="polite">
            {STAGE_LABELS[run.stage]}
          </h2>
        </div>
        <span className="elapsed">
          <Icon name="clock" />
          {Math.floor(elapsed / 60)}:{String(elapsed % 60).padStart(2, "0")}
        </span>
      </div>
      <p className="progressExplanation">
        {reconnecting
          ? "Connection interrupted. This is the last confirmed step; reconnecting automatically. Your query is saved."
          : run.stage === "queued"
            ? "Another design is using the local model. This query will start when it is available."
            : "Your query is saved. You can refresh this page or browse another saved query while this runs."}
      </p>
      <ol className="stageTimeline">
        {timeline(run).map((item) => (
          <li
            key={item.stage}
            className={"stageItem " + item.state}
            aria-current={item.state === "current" ? "step" : undefined}
          >
            <span className="stageIndicator">
              {item.state === "done" ? (
                <Icon name="check" />
              ) : item.state === "current" ? (
                <span />
              ) : null}
            </span>
            <span>{STAGE_LABELS[item.stage]}</span>
            <small>
              {item.state === "done"
                ? "Done"
                : item.state === "current"
                  ? "Running"
                  : "Next"}
            </small>
          </li>
        ))}
      </ol>
      {current && (
        <p className="progressTimestamp">
          Latest step started at{" "}
          {new Date(current.at).toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
          })}
          . Local generation can take several minutes.
        </p>
      )}
    </section>
  );
}
