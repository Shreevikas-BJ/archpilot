import { request as requestBackend } from "undici";

// Only imported by server routes; the browser never receives backend credentials.
export function backendRequestHeaders(includeJson = false) {
  const headers: Record<string, string> = {};
  if (includeJson) headers["Content-Type"] = "application/json";
  const proxyToken = process.env.ARCHPILOT_PROXY_TOKEN;
  if (proxyToken) headers["X-ArchPilot-Proxy-Token"] = proxyToken;
  return headers;
}

export async function proxyBackendRead(request: Request, path: string) {
  return proxyBackendRequest(request, path, "GET");
}

export async function proxyBackendWrite(request: Request, path: string) {
  return proxyBackendRequest(request, path, "POST");
}

async function proxyBackendRequest(
  request: Request,
  path: string,
  method: "GET" | "POST",
) {
  const baseUrl = process.env.BACKEND_API_URL;
  if (!baseUrl)
    return Response.json(
      { detail: "Backend is not configured" },
      { status: 503 },
    );
  try {
    const response = await requestBackend(
      `${baseUrl.replace(/\/$/, "")}${path}`,
      {
        method,
        ...(method === "POST"
          ? {
              body: await request.text(),
              headers: backendRequestHeaders(true),
            }
          : { headers: backendRequestHeaders() }),
        headersTimeout: 10_000,
        bodyTimeout: 10_000,
        signal: AbortSignal.any([request.signal, AbortSignal.timeout(10_000)]),
      },
    );
    return new Response(await response.body.text(), {
      status: response.statusCode,
      headers: {
        "Content-Type": "application/json",
        "Cache-Control": "no-store",
      },
    });
  } catch {
    return Response.json(
      {
        detail:
          "Backend unavailable. Check that the local services are running.",
      },
      { status: 503 },
    );
  }
}
