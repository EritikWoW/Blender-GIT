from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
from pathlib import Path
import sys
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from protocol import BlenderCommand

DEFAULT_MCP_DIR = os.environ.get(
    "BLENDER_MCP_DIR",
    r"E:\GPT_Tunel\blender-codex-mcp",
)


def _write_result(result: Any, out_path: Path) -> dict[str, Any]:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = result.model_dump(mode="json") if hasattr(result, "model_dump") else result

    if isinstance(payload, dict):
        content = payload.get("content")
        if isinstance(content, list):
            for index, item in enumerate(content):
                if not isinstance(item, dict) or item.get("type") != "image":
                    continue
                data = item.get("data")
                if not data:
                    continue
                mime = item.get("mimeType") or item.get("mime_type") or "image/png"
                ext = ".jpg" if "jpeg" in mime else ".png"
                image_path = out_path.parent / f"image_{index}{ext}"
                image_path.write_bytes(base64.b64decode(data))
                item["data"] = None
                item["saved_file"] = image_path.name

    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return payload


async def run(command: BlenderCommand, mcp_dir: str, out_path: Path) -> int:
    server = StdioServerParameters(
        command="uv",
        args=[
            "--directory",
            mcp_dir,
            "run",
            "blender-codex-mcp",
        ],
        env={
            **os.environ,
            "BLENDER_HOST": os.environ.get("BLENDER_HOST", "localhost"),
            "BLENDER_PORT": os.environ.get("BLENDER_PORT", "9876"),
            "DISABLE_TELEMETRY": "true",
        },
    )

    async with stdio_client(server) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.call_tool(command.tool, arguments=command.args)

    payload = _write_result(result, out_path)
    print(json.dumps(payload, ensure_ascii=False))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--command", required=True)
    parser.add_argument("--mcp-dir", default=DEFAULT_MCP_DIR)
    parser.add_argument("--out", default="bridge/out/result.json")
    args = parser.parse_args()

    command = BlenderCommand.parse(args.command)
    return asyncio.run(run(command, args.mcp_dir, Path(args.out)))


if __name__ == "__main__":
    sys.exit(main())
