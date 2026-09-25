import bpy
import math
import zipfile
from pathlib import Path
from mathutils import Vector

# ------------------------------------------------------------
# Project paths injected by bridge/run_project
# ------------------------------------------------------------
MODELS_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ------------------------------------------------------------
# Find or extract a real humanoid .blend asset
# ------------------------------------------------------------
blend_files = sorted(MODELS_DIR.rglob("*.blend"))

if not blend_files:
    zip_files = sorted(MODELS_DIR.glob("*.zip"))
    for archive in zip_files:
        extract_dir = MODELS_DIR / archive.stem
        extract_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive, "r") as zf:
            zf.extractall(extract_dir)
    blend_files = sorted(MODELS_DIR.rglob("*.blend"))

if not blend_files:
    raise RuntimeError(
        "No .blend humanoid asset found. Put the downloaded Sketchfab ZIP or .blend "
        "inside projects/traveler_character/assets/models/"
    )

source_blend = blend_files[0]
print("using_humanoid_asset", source_blend)

# ------------------------------------------------------------
# Clean current scene
# ------------------------------------------------------------
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)

for datablocks in (
    bpy.data.meshes,
    bpy.data.curves,
    bpy.data.armatures,
    bpy.data.cameras,
    bpy.data.lights,
):
    # Do not aggressively remove materials/images: imported file may reference them
    pass

scene = bpy.context.scene
scene.render.engine = "BLENDER_EEVEE"
scene.render.resolution_x = 900
scene.render.resolution_y = 1200
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.view_settings.exposure = 0.0

# ------------------------------------------------------------
# Append all objects from source .blend
# ------------------------------------------------------------
with bpy.data.libraries.load(str(source_blend), link=False) as (data_from, data_to):
    data_to.objects = list(data_from.objects)

imported = [obj for obj in data_to.objects if obj is not None]

for obj in imported:
    if obj.name not in bpy.context.collection.objects:
        try:
            bpy.context.collection.objects.link(obj)
        except RuntimeError:
            pass

if not imported:
    raise RuntimeError(f"No objects were imported from {source_blend}")

print("imported_objects", len(imported), [o.name for o in imported[:20]])

# Remove source cameras/lights so we control presentation.
for obj in list(imported):
    if obj.type in {"CAMERA", "LIGHT"}:
        bpy.data.objects.remove(obj, do_unlink=True)

imported = [o for o in imported if o.name in bpy.data.objects]

# ------------------------------------------------------------
# Put imported hierarchy under one root without destroying rigs
# ------------------------------------------------------------
root = bpy.data.objects.new("TravelerAssetRoot", None)
bpy.context.collection.objects.link(root)

top_level = [o for o in imported if o.parent is None]
for obj in top_level:
    obj.parent = root

bpy.context.view_layer.update()

# ------------------------------------------------------------
# Normalize model to human scale and ground it
# ------------------------------------------------------------
def mesh_world_bounds(objects):
    pts = []
    for obj in objects:
        if obj.type != "MESH":
            continue
        for corner in obj.bound_box:
            pts.append(obj.matrix_world @ Vector(corner))
    if not pts:
        raise RuntimeError("Imported asset has no mesh geometry")
    min_v = Vector((
        min(p.x for p in pts),
        min(p.y for p in pts),
        min(p.z for p in pts),
    ))
    max_v = Vector((
        max(p.x for p in pts),
        max(p.y for p in pts),
        max(p.z for p in pts),
    ))
    return min_v, max_v

min_v, max_v = mesh_world_bounds(imported)
height = max_v.z - min_v.z
if height <= 1e-6:
    raise RuntimeError("Imported model has invalid height")

TARGET_HEIGHT = 3.55
factor = TARGET_HEIGHT / height
root.scale = (factor, factor, factor)
bpy.context.view_layer.update()

min_v, max_v = mesh_world_bounds(imported)
center_x = (min_v.x + max_v.x) * 0.5
center_y = (min_v.y + max_v.y) * 0.5
root.location.x -= center_x
root.location.y -= center_y
root.location.z -= min_v.z
bpy.context.view_layer.update()

# Rotate only if model is obviously lying down.
min_v, max_v = mesh_world_bounds(imported)
dims = max_v - min_v
if dims.z < max(dims.x, dims.y) * 0.70:
    root.rotation_euler.x = math.radians(90)
    bpy.context.view_layer.update()
    min_v, max_v = mesh_world_bounds(imported)
    center_x = (min_v.x + max_v.x) * 0.5
    center_y = (min_v.y + max_v.y) * 0.5
    root.location.x -= center_x
    root.location.y -= center_y
    root.location.z -= min_v.z
    bpy.context.view_layer.update()

# ------------------------------------------------------------
# Ground / studio
# ------------------------------------------------------------
def make_mat(name, color, roughness=0.7):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name=name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = color
        bsdf.inputs["Roughness"].default_value = roughness
    return mat

ground_mat = make_mat("Ground", (0.018, 0.025, 0.020, 1.0), 0.95)

bpy.ops.mesh.primitive_plane_add(size=14, location=(0, 0, 0))
ground = bpy.context.active_object
ground.name = "Ground"
ground.data.materials.append(ground_mat)

world = scene.world
if world is None:
    world = bpy.data.worlds.new("World")
    scene.world = world
world.use_nodes = True
bg = world.node_tree.nodes.get("Background")
if bg:
    bg.inputs[0].default_value = (0.008, 0.012, 0.018, 1.0)
    bg.inputs[1].default_value = 0.22

def look_at(obj, target):
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()

# neutral key
bpy.ops.object.light_add(type="AREA", location=(3.0, -4.2, 5.3))
key = bpy.context.active_object
key.data.energy = 420
key.data.size = 4.0
key.data.color = (1.0, 0.90, 0.80)
look_at(key, (0, 0, 1.8))

# cool fill
bpy.ops.object.light_add(type="AREA", location=(-3.2, -1.3, 3.8))
fill = bpy.context.active_object
fill.data.energy = 180
fill.data.size = 3.5
fill.data.color = (0.35, 0.48, 1.0)
look_at(fill, (0, 0, 1.7))

# rim
bpy.ops.object.light_add(type="AREA", location=(0.8, 3.5, 4.6))
rim = bpy.context.active_object
rim.data.energy = 260
rim.data.size = 2.5
rim.data.color = (0.20, 0.52, 1.0)
look_at(rim, (0, 0, 2.0))

# ------------------------------------------------------------
# Camera
# ------------------------------------------------------------
bpy.ops.object.camera_add(location=(4.8, -6.4, 3.7))
cam = bpy.context.active_object
cam.name = "Camera"
cam.data.lens = 68
scene.camera = cam
look_at(cam, (0, 0, 1.75))

# ------------------------------------------------------------
# Save and render
# ------------------------------------------------------------
render_path = OUTPUT_DIR / "traveler_preview.png"
scene.render.filepath = str(render_path)
bpy.ops.render.render(write_still=True)

blend_path = OUTPUT_DIR / "traveler_character.blend"
bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))

print("real_humanoid_done", source_blend, render_path, blend_path)
