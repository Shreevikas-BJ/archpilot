import type {
  ArchitectureMode,
  ArchitectureResponse,
  DesignQuery,
  QuerySummary,
} from "./types";

export interface ArchitectureRequest {
  problem: string;
  mode: ArchitectureMode;
  clarifications: Record<string, string>;
}

export async function createArchitecture(
  request: ArchitectureRequest,
): Promise<ArchitectureResponse> {
  return apiRequest<ArchitectureResponse>("/api/architect", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
}

async function apiRequest<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, { cache: "no-store", ...init });
  let payload;
  try {
    payload = await response.json();
  } catch {
    throw new Error(
      "The server returned an unreadable response. Please try again.",
    );
  }
  if (!response.ok) {
    const detail: unknown = payload.detail;
    const message =
      typeof detail === "string"
        ? detail
        : Array.isArray(detail)
          ? detail.map((item) => item.msg ?? "Invalid request").join("; ")
          : "Architecture generation failed. Please try again.";
    throw new Error(message);
  }
  return payload as T;
}

export function getQueries(signal?: AbortSignal) {
  return apiRequest<QuerySummary[]>("/api/queries", { signal });
}
export function getQuery(queryId: string, signal?: AbortSignal) {
  return apiRequest<DesignQuery>(
    "/api/queries/" + encodeURIComponent(queryId),
    { signal },
  );
}
export function startDesignQuery(
  request: ArchitectureRequest,
  queryId?: string,
) {
  const path = queryId
    ? "/api/queries/" + encodeURIComponent(queryId) + "/runs"
    : "/api/queries";
  return apiRequest<DesignQuery>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
}
