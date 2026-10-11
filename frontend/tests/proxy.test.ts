import assert from "node:assert/strict";
import { afterEach, beforeEach, test } from "node:test";
import { getGlobalDispatcher, MockAgent, setGlobalDispatcher } from "undici";
import { GET, POST } from "../app/api/architect/route";
import { GET as getSaved } from "../app/api/architect/[runId]/route";
import { GET as getHealth } from "../app/api/health/route";

const originalDispatcher = getGlobalDispatcher();
const originalUrl = process.env.BACKEND_API_URL;
const originalTimeout = process.env.BACKEND_TIMEOUT_SECONDS;
const originalProxyToken = process.env.ARCHPILOT_PROXY_TOKEN;
let backend: MockAgent;

beforeEach(() => {
  backend = new MockAgent();
  backend.disableNetConnect();
  setGlobalDispatcher(backend);
  process.env.BACKEND_API_URL = "http://backend.test/";
  process.env.ARCHPILOT_PROXY_TOKEN = "demo-secret";
  delete process.env.BACKEND_TIMEOUT_SECONDS;
});

afterEach(async () => {
  setGlobalDispatcher(originalDispatcher);
  await backend.close();
  if (originalUrl === undefined) delete process.env.BACKEND_API_URL;
  else process.env.BACKEND_API_URL = originalUrl;
  if (originalTimeout === undefined) delete process.env.BACKEND_TIMEOUT_SECONDS;
  else process.env.BACKEND_TIMEOUT_SECONDS = originalTimeout;
  if (originalProxyToken === undefined)
    delete process.env.ARCHPILOT_PROXY_TOKEN;
  else process.env.ARCHPILOT_PROXY_TOKEN = originalProxyToken;
});

function request(
  body = { problem: "Build an internal staff directory", mode: "balanced" },
) {
  return new Request("http://frontend.test/api/architect", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

test("forwards the request and response with a timeout long enough for local generation", async () => {
  const input = request();
  const payload = await input.clone().text();
  const output = { run_id: "saved-run", status: "complete" };
  const dispatch = backend.dispatch.bind(backend);
  backend.dispatch = (options, handler) => {
    assert.equal(options.headersTimeout, 3_600_000);
    assert.equal(options.bodyTimeout, 3_600_000);
    return dispatch(options, handler);
  };
  backend
    .get("http://backend.test")
    .intercept({
      path: "/v1/architectures",
      method: "POST",
      body: payload,
      headers: { "x-archpilot-proxy-token": "demo-secret" },
    })
    .reply(200, output, { headers: { "content-type": "application/json" } });

  const response = await POST(input);
  assert.equal(response.status, 200);
  assert.equal(response.headers.get("cache-control"), "no-store");
  assert.deepEqual(await response.json(), output);
  backend.assertNoPendingInterceptors();
});

test("preserves FastAPI validation errors", async () => {
  const output = {
    detail: [{ loc: ["body", "problem"], msg: "String too short" }],
  };
  backend
    .get("http://backend.test")
    .intercept({
      path: "/v1/architectures",
      method: "POST",
    })
    .reply(422, output);
  const response = await POST(request());
  assert.equal(response.status, 422);
  assert.deepEqual(await response.json(), output);
});

test("returns a clear 502 when the backend cannot be reached", async () => {
  const response = await POST(request());
  assert.equal(response.status, 502);
  assert.match((await response.json()).detail, /Could not reach/);
});

test("returns 504 when the configured generation deadline expires", async () => {
  process.env.BACKEND_TIMEOUT_SECONDS = "0.02";
  backend
    .get("http://backend.test")
    .intercept({
      path: "/v1/architectures",
      method: "POST",
    })
    .reply(200, { status: "complete" })
    .delay(200);
  const response = await POST(request());
  assert.equal(response.status, 504);
  assert.match((await response.json()).detail, /timed out/);
});

test("rejects missing backend configuration before sending a request", async () => {
  delete process.env.BACKEND_API_URL;
  assert.equal((await POST(request())).status, 500);
});

test("rejects an invalid proxy timeout", async () => {
  process.env.BACKEND_TIMEOUT_SECONDS = "invalid";
  assert.equal((await POST(request())).status, 500);
});

test("loads recent saved designs without caching", async () => {
  const output = [{ run_id: "demo", title: "Directory" }];
  backend
    .get("http://backend.test")
    .intercept({
      path: "/v1/architectures?limit=20",
      method: "GET",
      headers: { "x-archpilot-proxy-token": "demo-secret" },
    })
    .reply(200, output);
  const response = await GET(new Request("http://frontend.test/api/architect"));
  assert.equal(response.status, 200);
  assert.equal(response.headers.get("cache-control"), "no-store");
  assert.deepEqual(await response.json(), output);
});

test("preserves a missing saved design response", async () => {
  backend
    .get("http://backend.test")
    .intercept({ path: "/v1/architectures/missing", method: "GET" })
    .reply(404, { detail: "Saved architecture not found" });
  const response = await getSaved(
    new Request("http://frontend.test/api/architect/missing"),
    { params: Promise.resolve({ runId: "missing" }) },
  );
  assert.equal(response.status, 404);
});

test("reports health unavailable when the backend is offline", async () => {
  const response = await getHealth(
    new Request("http://frontend.test/api/health"),
  );
  assert.equal(response.status, 503);
  assert.match((await response.json()).detail, /Backend unavailable/);
});
