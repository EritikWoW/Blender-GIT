from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
from pathlib import Path
import re
import sys
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from protocol import BlenderCommand

DEFAULT_MCP_DIR = os.environ.get(
    "BLENDER_MCP_DIR",
    r"E:\GPT_Tunel\blender-codex-mcp",
)

REPO_ROOT = Path(__file__).resolve().parent.parent
PROJECTS_ROOT = REPO_ROOT / "projects"
PROJECT_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")


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


async def _call_execute_code(session: ClientSession, code: str):
    return await session.call_tool(
        "execute_blender_code",
        arguments={"code": code},
    )


def _safe_project_dir(project_name: str) -> Path:
    if not PROJECT_NAME_RE.fullmatch(project_name):
        raise ValueError("project name may contain only letters, numbers, dot, underscore and dash")

    project_dir = (PROJECTS_ROOT / project_name).resolve()
    projects_root = PROJECTS_ROOT.resolve()

    if project_dir.parent != projects_root:
        raise ValueError("invalid project path")

    return project_dir


async def _render_scene_preview(
    session: ClientSession,
    out_path: Path,
    args: dict[str, Any],
) -> dict[str, Any]:
    width = max(64, min(int(args.get("width", 800)), 1920))
    height = max(64, min(int(args.get("height", 450)), 1080))

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

    result = await _call_execute_code(session, code)

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
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


async def _run_project(
    session: ClientSession,
    out_path: Path,
    args: dict[str, Any],
) -> dict[str, Any]:
    project_name = str(args.get("project", "")).strip()
    if not project_name:
        raise ValueError("run_project requires 'project'")

    project_dir = _safe_project_dir(project_name)
    manifest_path = project_dir / "manifest.json"

    if not project_dir.exists():
        raise FileNotFoundError(f"Project not found: {project_dir}")
    if not manifest_path.exists():
        raise FileNotFoundError(f"manifest.json not found: {manifest_path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    entrypoint_rel = str(manifest.get("entrypoint", "scripts/build.py"))
    entrypoint_path = (project_dir / entrypoint_rel).resolve()
    if project_dir not in entrypoint_path.parents:
        raise ValueError("entrypoint must stay inside project directory")
    if not entrypoint_path.exists():
        raise FileNotFoundError(f"Entrypoint not found: {entrypoint_path}")

    output_rel = str(manifest.get("output_dir", "output"))
    output_dir = (project_dir / output_rel).resolve()
    if project_dir not in output_dir.parents:
        raise ValueError("output_dir must stay inside project directory")
    output_dir.mkdir(parents=True, exist_ok=True)

    script_code = entrypoint_path.read_text(encoding="utf-8")

    bootstrap = f"""
from pathlib import Path
import os

PROJECT_DIR = Path({str(project_dir)!r})
ASSETS_DIR = PROJECT_DIR / "assets"
TEXTURES_DIR = ASSETS_DIR / "textures"
MODELS_DIR = ASSETS_DIR / "models"
REFERENCES_DIR = ASSETS_DIR / "references"
OUTPUT_DIR = Path({str(output_dir)!r})

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

print("PROJECT_DIR", PROJECT_DIR)
print("OUTPUT_DIR", OUTPUT_DIR)
"""

    result = await _call_execute_code(session, bootstrap + "\n" + script_code)
    detail = result.model_dump(mode="json") if hasattr(result, "model_dump") else result

    produced_files = [
        str(p.relative_to(project_dir)).replace("\\", "/")
        for p in sorted(output_dir.rglob("*"))
        if p.is_file()
    ]

    payload = {
        "meta": {
            "bridge_tool": "run_project",
            "project": project_name,
            "project_dir": str(project_dir),
            "entrypoint": str(entrypoint_path),
            "output_dir": str(output_dir),
        },
        "content": [
            {
                "type": "text",
                "text": f"Project '{project_name}' executed successfully.",
            }
        ],
        "mcp_result": detail,
        "produced_files": produced_files,
        "is_error": False,
        "result_type": "complete",
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
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
            elif command.tool == "run_project":
                payload = await _run_project(session, out_path, command.args)
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
