# Bring your own compute

ArchPilot can run on a workstation, a private VM, AWS, another cloud, or
Kubernetes. The deployment contract uses standard containers and network APIs,
so application code does not depend on a particular cloud provider.

## Supported integration contract

| Responsibility | Interface | Examples |
| --- | --- | --- |
| Compute | OCI containers, Python 3.12, Node.js 22 | EC2, ECS, EKS, Azure VM/AKS, GCE/GKE, bare metal |
| Durable data | PostgreSQL through `DATABASE_URL` | Local PostgreSQL, RDS/Aurora PostgreSQL, Cloud SQL, Azure Database for PostgreSQL, Neon |
| Model inference | OpenAI-compatible `/v1/chat/completions` and `/v1/models` | llama.cpp, Ollama, vLLM, LiteLLM, private model gateway |
| Research | SearXNG JSON `/search` API | Same host, private container service, or shared private SearXNG |
| Frontend to API | HTTPS plus optional `X-ArchPilot-Proxy-Token` | Private container network, load balancer, VPN, tunnel, Vercel |

Cloud model services that do not expose an OpenAI-compatible API can sit behind
a private LiteLLM or equivalent gateway. The gateway handles provider
authentication while the agent orchestration and Bonsai prompts stay unchanged.

## Run on a VM, server, or local Docker host

Copy the deployment environment and replace every placeholder:

```powershell
Copy-Item .env.self-hosted.example .env.self-hosted
```

Use a long random `ARCHPILOT_PROXY_TOKEN`. Keep `.env.self-hosted` out of Git.
Then validate and start the application containers:

```powershell
docker compose --env-file .env.self-hosted -f compose.self-hosted.yml config
docker compose --env-file .env.self-hosted -f compose.self-hosted.yml build
docker compose --env-file .env.self-hosted -f compose.self-hosted.yml run --rm backend python -m app.preflight
docker compose --env-file .env.self-hosted -f compose.self-hosted.yml up -d --wait
```

The frontend is available on `FRONTEND_PORT`. FastAPI binds only to loopback on
`BACKEND_PORT`; publish the frontend through your existing HTTPS ingress. The
frontend container reaches FastAPI over a private Docker network and attaches
the shared token server-side.

To run PostgreSQL and SearXNG on the same Docker host, combine the existing
infrastructure file with the application file and use service DNS names:

```env
DATABASE_URL=postgresql+asyncpg://archpilot:archpilot@postgres:5432/archpilot
SEARXNG_URL=http://searxng:8080
LLM_BASE_URL=http://host.docker.internal:8080/v1
```

```powershell
docker compose --env-file .env.self-hosted -f docker-compose.yml -f compose.self-hosted.yml up -d --build --wait
```

On Linux, use the model host's private IP or add an explicit `host-gateway`
mapping if the model runs directly on the Docker host.

## AWS reference deployment

For a small private installation, run the two containers on one EC2 instance
and use RDS PostgreSQL. Keep Bonsai on a GPU EC2 instance in the same VPC, or on
the application host when it has a suitable NVIDIA GPU. Run SearXNG on the
application host or as a private ECS service.

For a managed container installation:

1. Build both Dockerfiles and push them to private ECR repositories.
2. Run the frontend and backend as separate ECS services. The backend currently
   needs one replica because its local-model job queue is process-local.
3. Give the frontend private service discovery access to the backend. Expose
   only the frontend through an HTTPS Application Load Balancer.
4. Use RDS or Aurora PostgreSQL with TLS and allow port 5432 only from the
   backend task security group.
5. Run the model on GPU EC2, ECS with EC2 GPU capacity, or EKS. Allow its port
   only from the backend security group.
6. Store `DATABASE_URL`, `LLM_API_KEY`, and `ARCHPILOT_PROXY_TOKEN` in Secrets
   Manager or SSM Parameter Store and inject them into the tasks.

An AWS environment would normally set:

```env
DEPLOYMENT_MODE=cloud
DEPLOYMENT_LABEL=AWS private VPC
LLM_DISPLAY_NAME=Bonsai 2 27B on GPU EC2
DATABASE_URL=postgresql+asyncpg://user:password@cluster.region.rds.amazonaws.com:5432/archpilot?ssl=require
LLM_BASE_URL=http://private-model.internal:8080/v1
SEARXNG_URL=http://private-search.internal:8080
```

Fargate can host the frontend and backend, but the Bonsai GPU process needs a
GPU-capable compute service. Do not expose PostgreSQL, SearXNG, or the raw model
endpoint to the public internet.

## Kubernetes and other clouds

Deploy each Dockerfile as a separate Deployment. Use a ClusterIP Service for
FastAPI, an Ingress for the frontend, a Secret for credentials, and a ConfigMap
for safe labels and endpoint URLs. Keep the backend at one replica until the
in-process job queue is replaced by a durable external worker.

The same images run on Azure, Google Cloud, DigitalOcean, private OpenShift, or
an on-premises Kubernetes cluster. Choose an always-on backend instance. A
scale-to-zero platform must provide CPU after the `202 Accepted` response,
because architecture generation continues in a background task.

## Hosted frontend with private compute

The frontend can remain on Vercel while FastAPI runs on any target above. Set
Vercel's server-only `BACKEND_API_URL` to the backend's HTTPS address and set the
same `ARCHPILOT_PROXY_TOKEN` on both sides. The browser never receives the
backend URL, database credentials, model key, or proxy token.

## Validation and operating limits

Run `python -m app.preflight` from the backend environment before each first
deployment. It checks PostgreSQL with `SELECT 1`, the model's `/v1/models`, and a
real SearXNG JSON query without printing credentials or endpoint URLs.

The current worker serializes generations for a single local or private model.
PostgreSQL preserves queries and completed designs, but in-flight jobs belong to
one backend process. Horizontal backend scaling requires a durable queue and
distributed ownership before increasing the replica count.
