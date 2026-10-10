import assert from "node:assert/strict";
import { afterEach, test } from "node:test";
import { createArchitecture, getQuery, startDesignQuery } from "../lib/api";

const originalFetch = globalThis.fetch;
const input = {
  problem: "Build an internal staff directory",
  mode: "balanced" as const,
  clarifications: {},
};
afterEach(() => {
  globalThis.fetch = originalFetch;
});

test("shows FastAPI validation messages instead of object strings", async () => {
  globalThis.fetch = async () =>
    Response.json({ detail: [{ msg: "String too short" }] }, { status: 422 });
  await assert.rejects(createArchitecture(input), /String too short/);
});

test("shows the proxy's timeout message", async () => {
  globalThis.fetch = async () =>
    Response.json(
      { detail: "Architecture generation timed out." },
      { status: 504 },
    );
  await assert.rejects(createArchitecture(input), /generation timed out/);
});

test("handles an HTML error response without leaking a JSON parse error", async () => {
  globalThis.fetch = async () =>
    new Response("<h1>Bad gateway</h1>", { status: 502 });
  await assert.rejects(createArchitecture(input), /unreadable response/);
});

test("clarification rounds continue inside the same saved query", async () => {
  const body = { ...input, clarifications: { "Budget?": "$50" } };
  globalThis.fetch = async (url, init) => {
    assert.equal(url, "/api/queries/parent-id/runs");
    assert.equal(init?.method, "POST");
    assert.deepEqual(JSON.parse(init?.body as string), body);
    return Response.json(
      { query_id: "parent-id", runs: [{ status: "queued" }] },
      { status: 202 },
    );
  };
  assert.equal(
    (await startDesignQuery(body, "parent-id")).query_id,
    "parent-id",
  );
});

test("refreshing progress reads the saved query and does not create another run", async () => {
  globalThis.fetch = async (url, init) => {
    assert.equal(url, "/api/queries/parent-id");
    assert.equal(init?.method, undefined);
    assert.equal(init?.cache, "no-store");
    return Response.json({
      query_id: "parent-id",
      runs: [{ stage: "evaluation" }],
    });
  };
  assert.equal((await getQuery("parent-id")).runs[0].stage, "evaluation");
});
