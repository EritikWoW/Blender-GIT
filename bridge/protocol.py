from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

ALLOWED_TOOLS = {
    "blender_health_check",
    "get_scene_info",
    "get_object_info",
    "get_viewport_screenshot",
    "render_scene_preview",
    "execute_blender_code",
    "export_glb",
}

@dataclass(frozen=True)
class BlenderCommand:
    tool: str
    args: dict[str, Any]

    @classmethod
    def parse(cls, raw: str) -> "BlenderCommand":
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("command must be a JSON object")

        tool = payload.get("tool")
        args = payload.get("args", {})

        if tool not in ALLOWED_TOOLS:
            raise ValueError(f"tool not allowed: {tool!r}")
        if not isinstance(args, dict):
            raise ValueError("args must be a JSON object")

        return cls(tool=tool, args=args)
