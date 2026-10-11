"""Start the configured local demo without reinstalling or replacing services.

Run from the repository root with backend/.venv/Scripts/python.exe.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
LOGS = ROOT / ".demo"
HIDDEN = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


def healthy(url: str, *, database: bool = False) -> bool:
    try:
        token = os.environ.get("ARCHPILOT_PROXY_TOKEN")
        request = Request(
            url,
            headers={"X-ArchPilot-Proxy-Token": token} if token else {},
        )
        with urlopen(request, timeout=3) as response:
            data = json.load(response)
        return data.get("status") == "ok" and (
            not database or data.get("database") == "ok"
        )
    except (OSError, URLError, ValueError):
        return False


def wait_for(label: str, check, timeout: int = 120) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if check():
            print(f"  {label}: ready", flush=True)
            return
        time.sleep(2)
    raise RuntimeError(f"{label} did not become ready. Check logs in {LOGS}.")


def port_in_use(port: int) -> bool:
    with socket.socket() as connection:
        connection.settimeout(1)
        return connection.connect_ex(("127.0.0.1", port)) == 0


def start(name: str, command: list[str], cwd: Path) -> None:
    LOGS.mkdir(exist_ok=True)
    with (
        (LOGS / f"{name}.stdout.log").open("ab") as out,
        (LOGS / f"{name}.stderr.log").open("ab") as err,
    ):
        process = subprocess.Popen(
            command,
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=out,
            stderr=err,
            creationflags=HIDDEN,
            start_new_session=os.name != "nt",
        )
    with (LOGS / "started-processes.jsonl").open("a", encoding="utf-8") as manifest:
        manifest.write(
            json.dumps({"service": name, "pid": process.pid, "time": time.time()})
            + "\n"
        )
    print(f"  Started {name} (PID {process.pid})", flush=True)


def docker_ready() -> bool:
    return (
        subprocess.run(
            ["docker", "info"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=HIDDEN,
            timeout=15,
        ).returncode
        == 0
    )


def needs_build() -> bool:
    marker = FRONTEND / ".next" / "BUILD_ID"
    if not marker.exists():
        return True
    built_at = marker.stat().st_mtime
    sources = [
        path
        for folder in ("app", "components", "lib")
        for path in (FRONTEND / folder).rglob("*")
        if path.is_file()
    ]
    sources.extend(
        FRONTEND / name
        for name in (
            "package-lock.json",
            "next.config.ts",
            "tsconfig.json",
            ".env.local",
        )
    )
    return any(path.exists() and path.stat().st_mtime > built_at for path in sources)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--build", action="store_true", help="Force a frontend production build"
    )
    parser.add_argument(
        "--llama-server",
        type=Path,
        help="Path to the installed llama-server executable",
    )
    parser.add_argument(
        "--model-file", type=Path, help="GGUF path if LLM_MODEL uses an alias"
    )
    parser.add_argument(
        "--context-size",
        type=int,
        default=18432,
        help="Local model context tokens (default: 18432; increase only with enough VRAM)",
    )
    args = parser.parse_args()
    if args.context_size < 16384:
        parser.error(
            "--context-size must be at least 16384 for the full architecture review"
        )
    sys.path.insert(0, str(BACKEND))
    from app.config import Settings

    settings = Settings()
    python = (
        BACKEND / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    )
    node = shutil.which("node")
    next_cli = FRONTEND / "node_modules/next/dist/bin/next"
    if (
        not python.exists()
        or not node
        or not next_cli.exists()
        or not shutil.which("docker")
    ):
        raise RuntimeError(
            "Install the backend/frontend dependencies, Node.js, and Docker first; see README.md."
        )
    frontend_env = FRONTEND / ".env.local"
    if not frontend_env.exists():
        frontend_env.write_text(
            "BACKEND_API_URL=http://127.0.0.1:8000\nBACKEND_TIMEOUT_SECONDS=3600\n",
            encoding="utf-8",
        )

    print("Starting ArchPilot demo...", flush=True)
    if not docker_ready():
        desktop = (
            Path(os.environ.get("PROGRAMFILES", "C:/Program Files"))
            / "Docker/Docker/Docker Desktop.exe"
        )
        if not desktop.exists():
            raise RuntimeError("Start your Docker engine, then run this command again.")
        start("docker-desktop", [str(desktop)], ROOT)
        wait_for("Docker", docker_ready, 150)
    subprocess.run(
        ["docker", "compose", "up", "-d", "--wait"],
        cwd=ROOT,
        check=True,
        creationflags=HIDDEN,
    )

    model_url = urlparse(settings.llm_base_url)
    model_health = settings.llm_base_url.removesuffix("/v1").rstrip("/") + "/health"
    if not healthy(model_health):
        if settings.llm_provider != "openai_compatible" or model_url.hostname not in {
            "127.0.0.1",
            "localhost",
        }:
            raise RuntimeError(
                "Start your configured model endpoint before launching the demo."
            )
        model_file = args.model_file or Path(settings.llm_model)
        server = (
            args.llama_server or model_file.parent / "runtime/llama/llama-server.exe"
        )
        if not server.is_file() or not model_file.is_file():
            raise RuntimeError(
                "Model is offline. Supply --llama-server and --model-file, or start Prism first."
            )
        model_port = model_url.port or 80
        if port_in_use(model_port):
            raise RuntimeError(
                f"Port {model_port} is occupied but the model is not healthy; inspect that service."
            )
        start(
            "bonsai",
            [
                str(server),
                "-m",
                str(model_file),
                "--alias",
                settings.llm_model,
                "--host",
                "127.0.0.1",
                "--port",
                str(model_port),
                "-c",
                str(args.context_size),
                "-ngl",
                "99",
                "-np",
                "1",
                "--reasoning-budget",
                str(
                    settings.llm_reasoning_budget_tokens
                    if settings.llm_reasoning_budget_tokens is not None
                    else 4096
                ),
            ],
            ROOT,
        )
        wait_for("Bonsai", lambda: healthy(model_health), 180)
    else:
        print("  Bonsai: reusing healthy configured endpoint", flush=True)

    backend_health = "http://127.0.0.1:8000/v1/health"
    if not healthy(backend_health, database=True):
        if port_in_use(8000):
            raise RuntimeError(
                "Port 8000 is occupied but the API/database is not healthy; inspect that service."
            )
        start(
            "backend",
            [
                str(python),
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                "8000",
            ],
            BACKEND,
        )
        wait_for("Backend + database", lambda: healthy(backend_health, database=True))
    else:
        print("  Backend + database: ready", flush=True)

    frontend_health = "http://127.0.0.1:3000/api/health"
    if port_in_use(3000):
        if not healthy(frontend_health, database=True):
            raise RuntimeError(
                "Port 3000 is occupied but the frontend proxy is not healthy; "
                "check frontend/.env.local."
            )
        if args.build or needs_build():
            raise RuntimeError(
                "Frontend is running with a potentially older build. "
                "Stop that Next.js process and run this command again."
            )
        print("  Frontend: reusing healthy production server", flush=True)
    else:
        if args.build or needs_build():
            print("  Building frontend...", flush=True)
            subprocess.run(
                [node, str(next_cli), "build"],
                cwd=FRONTEND,
                check=True,
                creationflags=HIDDEN,
            )
        start(
            "frontend",
            [node, str(next_cli), "start", "--hostname", "127.0.0.1", "--port", "3000"],
            FRONTEND,
        )
        wait_for(
            "Frontend proxy + backend + database",
            lambda: healthy(frontend_health, database=True),
        )
    print(
        "\nReady: http://127.0.0.1:3000\nAPI docs: http://127.0.0.1:8000/docs\n"
        "Open a saved design for an instant demo, or use the demo brief for a live run.",
        flush=True,
    )


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, subprocess.SubprocessError, OSError) as error:
        print(f"Demo startup failed: {error}", file=sys.stderr)
        sys.exit(1)
