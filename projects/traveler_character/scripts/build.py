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

def make_mat(name, color, roughness=0.7):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name=name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = color
        bsdf.inputs["Roughness"].default_value = roughness
    return mat

# ------------------------------------------------------------
# Traveler outfit generated from the real rigged body
# ------------------------------------------------------------
body_candidates = [o for o in imported if o.type == "MESH"]
if not body_candidates:
    raise RuntimeError("Humanoid asset contains no mesh body")
body = max(body_candidates, key=lambda o: len(o.data.polygons) if o.data else 0)

armature = None
for mod in body.modifiers:
    if mod.type == "ARMATURE" and getattr(mod, "object", None):
        armature = mod.object
        break
if armature is None and body.parent and body.parent.type == "ARMATURE":
    armature = body.parent

print("traveler_body", body.name, "armature", armature.name if armature else None)

skin_mat = make_mat("Traveler_Skin", (0.38, 0.16, 0.085, 1.0), 0.62)
shirt_mat = make_mat("Traveler_Linen", (0.63, 0.55, 0.40, 1.0), 0.93)
vest_mat = make_mat("Traveler_Vest", (0.12, 0.075, 0.045, 1.0), 0.92)
pants_mat = make_mat("Traveler_Pants", (0.055, 0.050, 0.050, 1.0), 0.94)
boots_mat = make_mat("Traveler_Boots", (0.11, 0.050, 0.022, 1.0), 0.82)
sash_mat = make_mat("Traveler_Sash", (0.16, 0.075, 0.035, 1.0), 0.90)
strap_mat = make_mat("Traveler_Strap", (0.10, 0.045, 0.020, 1.0), 0.78)
hair_mat = make_mat("Traveler_Hair", (0.018, 0.010, 0.006, 1.0), 0.82)

body.data.materials.clear()
body.data.materials.append(skin_mat)

group_names = {vg.index: vg.name for vg in body.vertex_groups}

def matches_group(name, prefixes):
    return any(name == p or name.startswith(p) for p in prefixes)

def create_shell(name, prefixes, material, zmin=None, zmax=None, offset=0.018, thickness=0.014):
    obj = body.copy()
    obj.data = body.data.copy()
    obj.name = name
    bpy.context.collection.objects.link(obj)

    obj.data.materials.clear()
    obj.data.materials.append(material)

    mask_group = obj.vertex_groups.new(name="OutfitMask")
    keep = []
    for v in body.data.vertices:
        world_z = (body.matrix_world @ v.co).z
        if zmin is not None and world_z < zmin:
            continue
        if zmax is not None and world_z > zmax:
            continue
        ok = False
        for g in v.groups:
            gn = group_names.get(g.group, "")
            if matches_group(gn, prefixes) and g.weight > 0.12:
                ok = True
                break
        if ok:
            keep.append(v.index)

    if not keep:
        bpy.data.objects.remove(obj, do_unlink=True)
        raise RuntimeError(f"No vertices selected for outfit shell {name}")

    mask_group.add(keep, 1.0, "REPLACE")

    mask = obj.modifiers.new("OutfitMask", "MASK")
    mask.vertex_group = mask_group.name

    shrink = obj.modifiers.new("BodyClearance", "SHRINKWRAP")
    shrink.target = body
    shrink.wrap_method = "NEAREST_SURFACEPOINT"
    shrink.wrap_mode = "OUTSIDE"
    shrink.offset = offset

    solid = obj.modifiers.new("ClothThickness", "SOLIDIFY")
    solid.thickness = thickness
    solid.offset = 1.0

    smooth = obj.modifiers.new("ClothSmooth", "SMOOTH")
    smooth.factor = 0.35
    smooth.iterations = 2

    return obj

shirt = create_shell(
    "Traveler_Shirt",
    ("spine", "shoulder", "upper_arm", "forearm"),
    shirt_mat,
    zmin=1.20,
    zmax=3.02,
    offset=0.020,
    thickness=0.018,
)

vest = create_shell(
    "Traveler_Vest",
    ("spine", "shoulder"),
    vest_mat,
    zmin=1.42,
    zmax=2.90,
    offset=0.042,
    thickness=0.022,
)

pants = create_shell(
    "Traveler_Pants",
    ("pelvis", "thigh", "shin"),
    pants_mat,
    zmin=0.48,
    zmax=1.82,
    offset=0.024,
    thickness=0.020,
)

boots = create_shell(
    "Traveler_Boots",
    ("shin", "foot", "toe", "heel"),
    boots_mat,
    zmin=0.0,
    zmax=0.78,
    offset=0.040,
    thickness=0.030,
)

def add_box(name, loc, dims, material, rotation=(0.0, 0.0, 0.0), bevel=0.025):
    bpy.ops.mesh.primitive_cube_add(location=loc, rotation=rotation)
    obj = bpy.context.active_object
    obj.name = name
    obj.dimensions = dims
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(material)
    bev = obj.modifiers.new("SoftEdges", "BEVEL")
    bev.width = bevel
    bev.segments = 3
    return obj

# Wide wrapped sash, hanging cloth ends, and diagonal leather strap.
sash = add_box("Traveler_Sash", (0.0, -0.01, 1.70), (0.92, 0.54, 0.22), sash_mat, bevel=0.035)
sash.parent = root

sash_end_a = add_box(
    "Traveler_SashEnd_A",
    (0.15, -0.30, 1.35),
    (0.16, 0.055, 0.62),
    sash_mat,
    rotation=(math.radians(4), math.radians(-5), math.radians(10)),
    bevel=0.018,
)
sash_end_a.parent = root

sash_end_b = add_box(
    "Traveler_SashEnd_B",
    (-0.03, -0.29, 1.31),
    (0.13, 0.050, 0.55),
    sash_mat,
    rotation=(math.radians(-3), math.radians(5), math.radians(-8)),
    bevel=0.018,
)
sash_end_b.parent = root

strap = add_box(
    "Traveler_CrossBodyStrap",
    (0.03, -0.39, 2.18),
    (0.11, 0.055, 1.62),
    strap_mat,
    rotation=(0.0, math.radians(7), math.radians(-24)),
    bevel=0.018,
)
strap.parent = root

# A few overlapping ellipsoids form a stylized dark hair mass.
def add_hair_blob(name, loc, scale):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=12, location=loc)
    o = bpy.context.active_object
    o.name = name
    o.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    o.data.materials.append(hair_mat)
    return o

for i, (loc, scale) in enumerate([
    ((0.00, 0.015, 3.39), (0.34, 0.30, 0.20)),
    ((-0.20, -0.015, 3.33), (0.18, 0.20, 0.23)),
    ((0.20, -0.010, 3.33), (0.18, 0.20, 0.23)),
    ((-0.10, -0.20, 3.38), (0.16, 0.10, 0.13)),
    ((0.10, -0.20, 3.38), (0.16, 0.10, 0.13)),
]):
    hb = add_hair_blob(f"Traveler_Hair_{i}", loc, scale)

# Short beard/stubble mass under the jaw.
beard = add_hair_blob("Traveler_Beard", (0.0, -0.245, 3.08), (0.23, 0.10, 0.15))

print("traveler_outfit_created", [shirt.name, vest.name, pants.name, boots.name, sash.name, strap.name])

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
render_path = OUTPUT_DIR / "traveler_outfit_preview.png"
scene.render.filepath = str(render_path)
bpy.ops.render.render(write_still=True)

blend_path = OUTPUT_DIR / "traveler_character_outfit.blend"
bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))

print("traveler_outfit_done", source_blend, render_path, blend_path)
