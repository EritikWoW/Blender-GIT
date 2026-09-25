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
import bmesh

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

skin_mat = make_mat("Traveler_Skin", (0.40, 0.18, 0.09, 1.0), 0.62)
shirt_mat = make_mat("Traveler_Linen", (0.68, 0.61, 0.48, 1.0), 0.92)
vest_mat = make_mat("Traveler_Vest", (0.13, 0.085, 0.050, 1.0), 0.92)
pants_mat = make_mat("Traveler_Pants", (0.055, 0.050, 0.047, 1.0), 0.95)
boots_mat = make_mat("Traveler_Boots", (0.12, 0.055, 0.022, 1.0), 0.82)
sash_mat = make_mat("Traveler_Sash", (0.17, 0.080, 0.035, 1.0), 0.90)
strap_mat = make_mat("Traveler_Strap", (0.10, 0.045, 0.020, 1.0), 0.76)
hair_mat = make_mat("Traveler_Hair", (0.018, 0.010, 0.006, 1.0), 0.82)

body.data.materials.clear()
body.data.materials.append(skin_mat)

group_names = {vg.index: vg.name for vg in body.vertex_groups}

def selected_by_groups(vertex, prefixes, min_weight=0.10):
    for g in vertex.groups:
        name = group_names.get(g.group, "")
        if any(name == p or name.startswith(p) for p in prefixes) and g.weight >= min_weight:
            return True
    return False

def create_body_shell(name, prefixes, material, zmin=None, zmax=None, clearance=0.022, thickness=0.018):
    obj = body.copy()
    obj.data = body.data.copy()
    obj.name = name
    bpy.context.collection.objects.link(obj)

    # Keep the original armature modifier so the garment follows the rig.
    # Delete non-garment geometry from the copied mesh itself.
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.verts.ensure_lookup_table()

    delete_verts = []
    for v in bm.verts:
        src = body.data.vertices[v.index]
        wz = (body.matrix_world @ src.co).z
        keep = selected_by_groups(src, prefixes)
        if zmin is not None and wz < zmin:
            keep = False
        if zmax is not None and wz > zmax:
            keep = False
        if not keep:
            delete_verts.append(v)

    bmesh.ops.delete(bm, geom=delete_verts, context="VERTS")
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()

    obj.data.materials.clear()
    obj.data.materials.append(material)

    shrink = obj.modifiers.new("BodyClearance", "SHRINKWRAP")
    shrink.target = body
    shrink.wrap_method = "NEAREST_SURFACEPOINT"
    shrink.wrap_mode = "OUTSIDE"
    shrink.offset = clearance

    solid = obj.modifiers.new("ClothThickness", "SOLIDIFY")
    solid.thickness = thickness
    solid.offset = 1.0

    smooth = obj.modifiers.new("ClothSmooth", "LAPLACIANSMOOTH")
    smooth.lambda_factor = 0.15
    smooth.iterations = 3

    for poly in obj.data.polygons:
        poly.use_smooth = True
    return obj

shirt = create_body_shell(
    "Traveler_Shirt",
    ("spine", "shoulder", "upper_arm", "forearm"),
    shirt_mat,
    zmin=1.18,
    zmax=2.98,
    clearance=0.030,
    thickness=0.018,
)

vest = create_body_shell(
    "Traveler_Vest",
    ("spine", "shoulder"),
    vest_mat,
    zmin=1.42,
    zmax=2.88,
    clearance=0.055,
    thickness=0.022,
)

pants = create_body_shell(
    "Traveler_Pants",
    ("pelvis", "thigh", "shin"),
    pants_mat,
    zmin=0.40,
    zmax=1.82,
    clearance=0.045,
    thickness=0.024,
)

boots = create_body_shell(
    "Traveler_Boots",
    ("shin", "foot", "toe", "heel"),
    boots_mat,
    zmin=0.0,
    zmax=0.72,
    clearance=0.060,
    thickness=0.032,
)

def rounded_box(name, loc, dims, material, rot=(0.0,0.0,0.0), bevel=0.035):
    bpy.ops.mesh.primitive_cube_add(location=loc, rotation=rot)
    obj = bpy.context.active_object
    obj.name = name
    obj.dimensions = dims
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(material)
    bev = obj.modifiers.new("SoftEdges", "BEVEL")
    bev.width = bevel
    bev.segments = 4
    return obj

def curve_strap(name, points, bevel_depth, material):
    curve = bpy.data.curves.new(name + "Curve", type="CURVE")
    curve.dimensions = "3D"
    curve.bevel_depth = bevel_depth
    curve.bevel_resolution = 4
    spline = curve.splines.new("BEZIER")
    spline.bezier_points.add(len(points) - 1)
    for bp, co in zip(spline.bezier_points, points):
        bp.co = co
        bp.handle_left_type = "AUTO"
        bp.handle_right_type = "AUTO"
    obj = bpy.data.objects.new(name, curve)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(material)
    return obj

# Wide sash around the waist. Keep it compact and close to the body.
sash = rounded_box("Traveler_Sash", (0.0, -0.015, 1.68), (0.92, 0.56, 0.20), sash_mat, bevel=0.040)
rounded_box("Traveler_SashEnd_A", (0.10, -0.33, 1.39), (0.13, 0.045, 0.48), sash_mat, rot=(math.radians(3),0,math.radians(8)), bevel=0.018)
rounded_box("Traveler_SashEnd_B", (-0.03, -0.33, 1.36), (0.11, 0.042, 0.42), sash_mat, rot=(math.radians(-2),0,math.radians(-7)), bevel=0.018)

# Shoulder strap from reference, kept thin.
curve_strap(
    "Traveler_CrossBodyStrap",
    [(-0.30,-0.365,2.75), (-0.14,-0.39,2.38), (0.08,-0.39,2.02), (0.25,-0.35,1.72)],
    0.026,
    strap_mat,
)

# Hair should frame the head, never cover the face.
bpy.ops.mesh.primitive_uv_sphere_add(segments=36, ring_count=18, location=(0.0, 0.055, 3.40))
hair = bpy.context.active_object
hair.name = "Traveler_Hair"
hair.scale = (0.305, 0.275, 0.145)
bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
hair.data.materials.append(hair_mat)

# Side/back locks only, no frontal beard ball.
for x, y, z, sc in [
    (-0.22,0.00,3.33,(0.09,0.12,0.20)),
    (0.22,0.00,3.33,(0.09,0.12,0.20)),
    (-0.17,0.08,3.30,(0.10,0.10,0.18)),
    (0.17,0.08,3.30,(0.10,0.10,0.18)),
]:
    bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=12, location=(x,y,z))
    lock = bpy.context.active_object
    lock.name = "Traveler_HairLock"
    lock.scale = sc
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    lock.data.materials.append(hair_mat)

# Small flattened stubble patch below the mouth, intentionally subtle.
bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=12, location=(0.0,-0.285,3.12))
stubble = bpy.context.active_object
stubble.name = "Traveler_Stubble"
stubble.scale = (0.16,0.028,0.10)
bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
stubble.data.materials.append(hair_mat)

print("traveler_outfit_created_v3", [shirt.name, vest.name, pants.name, boots.name])

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
