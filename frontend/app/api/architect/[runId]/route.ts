import { proxyBackendRead } from "../../../../lib/backend-proxy";

export const runtime = "nodejs";

export async function GET(
  request: Request,
  context: { params: Promise<{ runId: string }> },
) {
  const { runId } = await context.params;
  return proxyBackendRead(
    request,
    `/v1/architectures/${encodeURIComponent(runId)}`,
  );
}
