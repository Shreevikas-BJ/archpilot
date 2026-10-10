import assert from "node:assert/strict";
import { test } from "node:test";
import { timeline } from "../lib/progress";
import type { QueryRun } from "../lib/types";

test("progress reflects confirmed backend stages without advancing on elapsed time", () => {
  const run = {
    stage: "search",
    events: ["queued", "requirements", "research", "search"].map((stage) => ({
      stage,
      at: "2026-01-01T00:00:00Z",
    })),
  } as QueryRun;
  const states = Object.fromEntries(
    timeline(run).map((item) => [item.stage, item.state]),
  );
  assert.equal(states.requirements, "done");
  assert.equal(states.search, "current");
  assert.equal(states.architecture, "pending");
  assert.equal(states.critique, "pending");
  assert.equal(states.revision, undefined);
});

test("revision steps appear only when the backend actually enters them", () => {
  const run = {
    stage: "revision",
    events: [
      "requirements",
      "research",
      "search",
      "evaluation",
      "architecture",
      "critique",
      "revision",
    ].map((stage) => ({ stage, at: "2026-01-01T00:00:00Z" })),
  } as QueryRun;
  const states = Object.fromEntries(
    timeline(run).map((item) => [item.stage, item.state]),
  );
  assert.equal(states.critique, "done");
  assert.equal(states.revision, "current");
  assert.equal(states.final_review, undefined);
});
