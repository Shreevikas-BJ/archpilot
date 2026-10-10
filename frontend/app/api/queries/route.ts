import {
  proxyBackendRead,
  proxyBackendWrite,
} from "../../../lib/backend-proxy";
export const runtime = "nodejs";
export function GET(request: Request) {
  return proxyBackendRead(request, "/v1/queries");
}
export function POST(request: Request) {
  return proxyBackendWrite(request, "/v1/queries");
}
