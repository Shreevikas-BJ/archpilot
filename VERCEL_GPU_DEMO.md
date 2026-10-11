# Vercel frontend with local GPU inference

Vercel hosts the Next.js frontend and its server-side API routes. Those routes
call a Cloudflare quick tunnel that terminates at local FastAPI. FastAPI alone
can reach PostgreSQL, SearXNG, and the Bonsai llama.cpp endpoint on the local
machine.

```text
Browser -> Vercel Next.js -> authenticated HTTPS tunnel -> local FastAPI
                                                      |-> PostgreSQL
                                                      |-> SearXNG
                                                      `-> Bonsai / local GPU
```

The llama.cpp endpoint and database are never exposed directly. A random shared
secret protects every tunneled `/v1` request. The secret is stored only in the
ignored `.demo/vercel-proxy-token` file and Vercel's encrypted environment.

## Start the local side

Download the official Windows `cloudflared` executable to
`.demo/tools/cloudflared.exe`, then run from the repository root:

```powershell
.\scripts\start_vercel_gpu_demo.ps1 -Build
```

The script starts the normal local demo, generates or reuses the proxy token,
opens the quick tunnel, verifies FastAPI and PostgreSQL through that tunnel, and
writes connection metadata to `.demo/vercel-bridge.json`.

Set these server-only variables on the Vercel project for Preview and Production:

```env
BACKEND_API_URL=https://generated-name.trycloudflare.com
ARCHPILOT_PROXY_TOKEN=<contents of .demo/vercel-proxy-token>
BACKEND_TIMEOUT_SECONDS=3600
```

Deploy the `frontend/` directory. Use the deployed UI exactly as the local UI;
new queries return `202` quickly and the page polls the durable backend run.

## Demo availability

Cloudflare quick-tunnel URLs are temporary. Keep this computer, Docker, Prism,
FastAPI, and `cloudflared` running while the hosted demo is in use. After a
restart, rerun the script, update `BACKEND_API_URL` in Vercel, and redeploy. A
named Cloudflare Tunnel with an owned domain is the stable follow-up for a
persistent public demo.
