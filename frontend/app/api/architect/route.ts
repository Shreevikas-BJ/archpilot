import { request as requestBackend } from "undici";
import { proxyBackendRead } from "../../../lib/backend-proxy";

export const runtime = "nodejs";

export async function GET(request: Request) {
  return proxyBackendRead(request, "/v1/architectures?limit=20");
}

export async function POST(request: Request) {
  const backendUrl = process.env.BACKEND_API_URL;
  if (!backendUrl) {
    return Response.json(
      { detail: "BACKEND_API_URL is not configured" },
      { status: 500 },
    );
  }

  const timeoutSeconds = Number(process.env.BACKEND_TIMEOUT_SECONDS ?? "3600");
  if (
    !Number.isFinite(timeoutSeconds) ||
    timeoutSeconds <= 0 ||
    timeoutSeconds > 86400
  ) {
    return Response.json(
      { detail: "BACKEND_TIMEOUT_SECONDS is invalid" },
      { status: 500 },
    );
  }
  const timeoutMs = Math.ceil(timeoutSeconds * 1000);
  const deadline = AbortSignal.timeout(timeoutMs);
  const body = await request.text();

  try {
    // Bonsai can take several minutes. Override the HTTP client's header timeout
    // as well as bounding the whole request; a fetch AbortSignal alone is not enough.
    const response = await requestBackend(
      `${backendUrl.replace(/\/$/, "")}/v1/architectures`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body,
        headersTimeout: timeoutMs,
        bodyTimeout: timeoutMs,
        signal: AbortSignal.any([request.signal, deadline]),
      },
    );

    const payload = await response.body.text();
    const contentType = response.headers["content-type"];
    return new Response(payload, {
      status: response.statusCode,
      headers: {
        "Content-Type": Array.isArray(contentType)
          ? contentType[0]
          : (contentType ?? "application/json"),
        "Cache-Control": "no-store",
      },
    });
  } catch {
    return Response.json(
      {
        detail: deadline.aborted
          ? "Architecture generation timed out. Please try again."
          : "Could not reach the architecture backend",
      },
      { status: deadline.aborted ? 504 : 502 },
    );
  }
}
