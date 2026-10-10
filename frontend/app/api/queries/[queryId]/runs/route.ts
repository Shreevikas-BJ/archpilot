import { proxyBackendWrite } from "../../../../../lib/backend-proxy";
export async function POST(
  request: Request,
  context: { params: Promise<{ queryId: string }> },
) {
  const { queryId } = await context.params;
  return proxyBackendWrite(
    request,
    "/v1/queries/" + encodeURIComponent(queryId) + "/runs",
  );
}
