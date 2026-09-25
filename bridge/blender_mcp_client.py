from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import urllib.error
import urllib.request

from protocol import BlenderCommand

DEFAULT_ENDPOINT = os.environ.get("BLENDER_BRIDGE_URL", "http://127.0.0.1:9876")

def call_bridge(command: BlenderCommand, endpoint: str) -> dict:
    payload = json.dumps(
        {"tool": command.tool, "args": command.args},
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        endpoint.rstrip("/") + "/mcp",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Blender bridge HTTP {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Cannot reach local Blender bridge at {endpoint}: {exc}") from exc

    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return {"ok": True, "raw": body}

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--command", required=True)
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--out", default="bridge/out/result.json")
    args = parser.parse_args()

    command = BlenderCommand.parse(args.command)
    result = call_bridge(command, args.endpoint)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    sys.exit(main())
