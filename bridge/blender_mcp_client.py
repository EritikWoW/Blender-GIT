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


async def _render_scene_preview(
    session: ClientSession,
    out_path: Path,
    args: dict[str, Any],
) -> dict[str, Any]:
    width = int(args.get("width", 800))
    height = int(args.get("height", 450))
    width = max(64, min(width, 1920))
    height = max(64, min(height, 1080))

    image_path = (out_path.parent / "render.png").resolve()
    image_path.parent.mkdir(parents=True, exist_ok=True)

    code = f"""
import bpy

scene = bpy.context.scene
scene.render.resolution_x = {width}
scene.render.resolution_y = {height}
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = 'PNG'
scene.render.filepath = {str(image_path)!r}

if scene.camera is None:
    raise RuntimeError('Scene has no active camera')

bpy.ops.render.render(write_still=True)
print('render_saved', scene.render.filepath)
"""

    result = await session.call_tool(
        "execute_blender_code",
        arguments={"code": code},
    )

    if not image_path.exists():
        raise RuntimeError(f"Blender render did not create {image_path}")

    detail = result.model_dump(mode="json") if hasattr(result, "model_dump") else result
    payload = {
        "meta": {"bridge_tool": "render_scene_preview"},
        "content": [
            {
                "type": "image",
                "mime_type": "image/png",
                "data": None,
                "saved_file": image_path.name,
                "width": width,
                "height": height,
            },
            {
                "type": "text",
                "text": "Rendered active Blender camera to render.png",
            },
        ],
        "mcp_result": detail,
        "is_error": False,
        "result_type": "complete",
    }
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

            if command.tool == "render_scene_preview":
                payload = await _render_scene_preview(session, out_path, command.args)
            else:
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
