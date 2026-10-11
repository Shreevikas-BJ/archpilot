"""Container health probe that supports the optional proxy token."""

import json
import os
from urllib.request import Request, urlopen


def main() -> int:
    token = os.environ.get("ARCHPILOT_PROXY_TOKEN")
    request = Request(
        "http://127.0.0.1:8000/v1/health",
        headers={"X-ArchPilot-Proxy-Token": token} if token else {},
    )
    try:
        with urlopen(request, timeout=5) as response:
            payload = json.load(response)
        return int(
            payload.get("status") != "ok" or payload.get("database") != "ok"
        )
    except (OSError, ValueError):
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
