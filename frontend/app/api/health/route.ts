import { proxyBackendRead } from "../../../lib/backend-proxy";

export const runtime = "nodejs";

export async function GET(request: Request) {
  return proxyBackendRead(request, "/v1/health");
}
