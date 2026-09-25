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

# Cache body vertices in world space for measurements.
world_verts = [body.matrix_world @ v.co for v in body.data.vertices]
min_x = min(v.x for v in world_verts)
max_x = max(v.x for v in world_verts)
min_y = min(v.y for v in world_verts)
max_y = max(v.y for v in world_verts)
min_z = min(v.z for v in world_verts)
max_z = max(v.z for v in world_verts)

def section_bounds(z, half_window=0.055):
    pts = [v for v in world_verts if abs(v.z - z) <= half_window]
    if len(pts) < 8:
        pts = sorted(world_verts, key=lambda v: abs(v.z - z))[:64]
    return (
        min(p.x for p in pts),
        max(p.x for p in pts),
        min(p.y for p in pts),
        max(p.y for p in pts),
    )

def create_loft(name, z_levels, clearance_xy, material, segments=36, front_bias=0.0):
    verts = []
    faces = []
    for zi, z in enumerate(z_levels):
        sx0, sx1, sy0, sy1 = section_bounds(z)
        cx = (sx0 + sx1) * 0.5
        cy = (sy0 + sy1) * 0.5 + front_bias
        rx = max((sx1 - sx0) * 0.5 + clearance_xy, 0.05)
        ry = max((sy1 - sy0) * 0.5 + clearance_xy, 0.05)
        for i in range(segments):
            a = 2.0 * math.pi * i / segments
            verts.append((cx + math.cos(a) * rx, cy + math.sin(a) * ry, z))
    rings = len(z_levels)
    for r in range(rings - 1):
        for i in range(segments):
            a = r * segments + i
            b = r * segments + (i + 1) % segments
            c = (r + 1) * segments + (i + 1) % segments
            d = (r + 1) * segments + i
            faces.append((a, b, c, d))
    # clean caps
    bottom_center = len(verts)
    verts.append(tuple(sum((Vector(v) for v in verts[:segments]), Vector()) / segments))
    top_ring_start = (rings - 1) * segments
    top_center = len(verts)
    verts.append(tuple(sum((Vector(verts[top_ring_start+i]) for i in range(segments)), Vector()) / segments))
    for i in range(segments):
        faces.append((bottom_center, (i + 1) % segments, i))
        a = top_ring_start + i
        b = top_ring_start + (i + 1) % segments
        faces.append((top_center, a, b))
    mesh = bpy.data.meshes.new(name + "Mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(material)
    bev = obj.modifiers.new("GarmentSoftness", "BEVEL")
    bev.width = 0.018
    bev.segments = 2
    smooth = obj.modifiers.new("GarmentSmooth", "SMOOTH")
    smooth.factor = 0.20
    smooth.iterations = 2
    for poly in obj.data.polygons:
        poly.use_smooth = True
    return obj

def cone_between(name, p1, p2, r1, r2, material, vertices=32):
    p1 = Vector(p1)
    p2 = Vector(p2)
    mid = (p1 + p2) * 0.5
    vec = p2 - p1
    depth = vec.length
    bpy.ops.mesh.primitive_cone_add(
        vertices=vertices,
        radius1=r1,
        radius2=r2,
        depth=depth,
        location=mid,
    )
    obj = bpy.context.active_object
    obj.name = name
    obj.rotation_euler = vec.to_track_quat("Z", "Y").to_euler()
    obj.data.materials.append(material)
    bev = obj.modifiers.new("SoftEdges", "BEVEL")
    bev.width = 0.018
    bev.segments = 3
    for poly in obj.data.polygons:
        poly.use_smooth = True
    return obj

def rounded_box(name, loc, dims, material, rot=(0.0,0.0,0.0), bevel=0.04):
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

# Remove previous generated outfit from this build if present.
for obj in list(bpy.data.objects):
    if obj.name.startswith("Traveler_") and obj is not body:
        bpy.data.objects.remove(obj, do_unlink=True)

# Shirt: clean tapered torso, not a raw masked body shell.
shirt = create_loft(
    "Traveler_Shirt",
    [1.34, 1.58, 1.90, 2.22, 2.52, 2.78, 2.94],
    0.055,
    shirt_mat,
    front_bias=-0.008,
)

# Sleeves follow the actual armature bones.
def bone_world(name):
    if armature and name in armature.data.bones:
        b = armature.data.bones[name]
        return armature.matrix_world @ b.head_local, armature.matrix_world @ b.tail_local
    return None

for side in ("L", "R"):
    upper = bone_world(f"upper_arm.{side}")
    fore = bone_world(f"forearm.{side}")
    if upper and fore:
        shoulder = upper[0]
        elbow = upper[1]
        wrist = fore[1]
        cone_between(f"Traveler_ShirtUpper_{side}", shoulder, elbow, 0.20, 0.17, shirt_mat)
        cone_between(f"Traveler_ShirtFore_{side}", elbow, wrist, 0.17, 0.13, shirt_mat)
        # rolled cuff
        cuff_mid = wrist.lerp(elbow, 0.20)
        axis = (elbow - wrist).normalized()
        cone_between(
            f"Traveler_Cuff_{side}",
            cuff_mid - axis * 0.055,
            cuff_mid + axis * 0.055,
            0.145,
            0.145,
            shirt_mat,
        )

# Vest: shorter, darker layer over the shirt.
vest = create_loft(
    "Traveler_Vest",
    [1.46, 1.72, 2.02, 2.34, 2.62, 2.82],
    0.085,
    vest_mat,
    front_bias=0.018,
)
# flatten/open the very front visually with two darker long lapel panels
rounded_box("Traveler_VestPanel_L", (-0.24, -0.405, 2.10), (0.22, 0.055, 1.36), vest_mat, rot=(0,0,math.radians(3)), bevel=0.025)
rounded_box("Traveler_VestPanel_R", (0.24, -0.405, 2.10), (0.22, 0.055, 1.36), vest_mat, rot=(0,0,math.radians(-3)), bevel=0.025)

# V-shaped shirt collar / opening.
curve_strap("Traveler_Collar_L", [(-0.11,-0.390,2.92), (-0.06,-0.415,2.80), (0.00,-0.425,2.66)], 0.018, shirt_mat)
curve_strap("Traveler_Collar_R", [(0.11,-0.390,2.92), (0.06,-0.415,2.80), (0.00,-0.425,2.66)], 0.018, shirt_mat)

# Pants are deliberately loose tapered tubes, no anatomical toes/genitals.
hip_l = Vector((-0.19, 0.0, 1.55))
hip_r = Vector((0.19, 0.0, 1.55))
ankle_l = Vector((-0.17, 0.0, 0.42))
ankle_r = Vector((0.17, 0.0, 0.42))
if armature:
    b = bone_world("thigh.L")
    if b: hip_l = b[0]
    b = bone_world("thigh.R")
    if b: hip_r = b[0]
    b = bone_world("shin.L")
    if b: ankle_l = b[1]
    b = bone_world("shin.R")
    if b: ankle_r = b[1]
pants_l = cone_between("Traveler_Pants_L", hip_l + Vector((0,0,0.05)), ankle_l + Vector((0,0,0.10)), 0.245, 0.165, pants_mat)
pants_r = cone_between("Traveler_Pants_R", hip_r + Vector((0,0,0.05)), ankle_r + Vector((0,0,0.10)), 0.245, 0.165, pants_mat)

# Wide wrapped sash hides waist transitions cleanly.
sash = create_loft(
    "Traveler_Sash",
    [1.56, 1.64, 1.72, 1.80],
    0.115,
    sash_mat,
    front_bias=-0.012,
)
rounded_box("Traveler_SashEnd_A", (0.11, -0.420, 1.36), (0.15, 0.050, 0.62), sash_mat, rot=(math.radians(4),0,math.radians(8)), bevel=0.018)
rounded_box("Traveler_SashEnd_B", (-0.02, -0.425, 1.31), (0.13, 0.045, 0.54), sash_mat, rot=(math.radians(-3),0,math.radians(-8)), bevel=0.018)

# Boots: separate shafts + shoe bodies, intentionally hide anatomical feet.
for side, x in (("L",-0.17),("R",0.17)):
    shaft = cone_between(
        f"Traveler_BootShaft_{side}",
        (x, 0.0, 0.12),
        (x, 0.0, 0.72),
        0.19,
        0.17,
        boots_mat,
    )
    rounded_box(
        f"Traveler_BootFoot_{side}",
        (x, -0.085, 0.10),
        (0.34, 0.50, 0.22),
        boots_mat,
        bevel=0.055,
    )

# Cross-body leather strap, curved and measured in world space.
curve_strap(
    "Traveler_CrossBodyStrap",
    [(-0.34,-0.430,2.78), (-0.12,-0.455,2.35), (0.15,-0.455,1.88), (0.30,-0.420,1.64)],
    0.032,
    strap_mat,
)

# Hair cap and short beard, positioned from the known 3.55 m body bounds.
bpy.ops.mesh.primitive_uv_sphere_add(segments=36, ring_count=18, location=(0.0, 0.015, 3.37))
hair = bpy.context.active_object
hair.name = "Traveler_Hair"
hair.scale = (0.31, 0.29, 0.19)
bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
hair.data.materials.append(hair_mat)

for x, y, z, sc in [
    (-0.20,-0.04,3.32,(0.13,0.12,0.20)),
    (0.20,-0.04,3.32,(0.13,0.12,0.20)),
    (-0.10,-0.22,3.38,(0.13,0.07,0.10)),
    (0.10,-0.22,3.38,(0.13,0.07,0.10)),
]:
    bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=12, location=(x,y,z))
    lock = bpy.context.active_object
    lock.name = "Traveler_HairLock"
    lock.scale = sc
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    lock.data.materials.append(hair_mat)

bpy.ops.mesh.primitive_uv_sphere_add(segments=28, ring_count=14, location=(0.0,-0.245,3.08))
beard = bpy.context.active_object
beard.name = "Traveler_Beard"
beard.scale = (0.22,0.075,0.15)
bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
beard.data.materials.append(hair_mat)

print("traveler_outfit_created_v2")

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
