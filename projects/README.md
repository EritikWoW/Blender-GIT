# Blender projects

Each project is a self-contained workspace checked out by the self-hosted runner.

Structure:

- manifest.json
- scripts/
- assets/textures/
- assets/models/
- assets/references/
- output/

Run a project from the command bus:

```text
/blender {"tool":"run_project","args":{"project":"_template"}}
```

The runner checks out the repository first, so all committed scripts and assets are available locally before Blender execution begins.
