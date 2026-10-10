import { proxyBackendRead } from "../../../../lib/backend-proxy";
export async function GET(
  request: Request,
  context: { params: Promise<{ queryId: string }> },
) {
  const { queryId } = await context.params;
  return proxyBackendRead(
    request,
    "/v1/queries/" + encodeURIComponent(queryId),
  );
}
