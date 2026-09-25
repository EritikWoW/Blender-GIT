# Blender-GIT

GitHub command bridge between ChatGPT and a local Blender 5.2 instance.

## Architecture

ChatGPT -> GitHub issue command -> GitHub Actions -> self-hosted Windows runner -> local Blender bridge -> Blender -> result comment/artifact.

## Security model

- Dedicated self-hosted runner label: `blender-local`
- Dispatcher only accepts commands from repository owner
- Commands are JSON, not arbitrary PowerShell
- Allowed operations are explicitly whitelisted by the bridge
- Local Blender endpoint defaults to `127.0.0.1:9876`
- Results are written to `bridge/out`

## Runner setup

Register a self-hosted Windows runner for this repository and add label:

`blender-local`

Install Python 3.11+ on the runner.

## Command format

Post a comment to the command-bus issue:

```text
/blender {"tool":"get_scene_info","args":{}}
```

Examples:

```text
/blender {"tool":"get_viewport_screenshot","args":{}}
```

```text
/blender {"tool":"execute_blender_code","args":{"code":"import bpy\nprint(list(bpy.data.objects.keys()))"}}
```

The bridge intentionally rejects unknown tools.
