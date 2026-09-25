import bpy
import bmesh
import math
import zipfile
from pathlib import Path
from mathutils import Vector

MODELS_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ------------------------------------------------------------
# Load real humanoid source asset
# ------------------------------------------------------------
blend_files = sorted(MODELS_DIR.rglob("*.blend"))
if not blend_files:
    for archive in sorted(MODELS_DIR.glob("*.zip")):
        extract_dir = MODELS_DIR / archive.stem
        extract_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive, "r") as zf:
            zf.extractall(extract_dir)
    blend_files = sorted(MODELS_DIR.rglob("*.blend"))

if not blend_files:
    raise RuntimeError("No humanoid .blend asset found in assets/models")

source_blend = blend_files[0]
print("using_humanoid_asset", source_blend)

bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)

scene = bpy.context.scene
scene.render.engine = "BLENDER_EEVEE"
scene.render.resolution_x = 900
scene.render.resolution_y = 1200
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.view_settings.exposure = 0.0

with bpy.data.libraries.load(str(source_blend), link=False) as (data_from, data_to):
    data_to.objects = list(data_from.objects)

imported = [o for o in data_to.objects if o is not None]
for obj in imported:
    try:
        bpy.context.collection.objects.link(obj)
    except RuntimeError:
        pass

if not imported:
    raise RuntimeError("Humanoid source contained no objects")

for obj in list(imported):
    if obj.type in {"CAMERA", "LIGHT"}:
        bpy.data.objects.remove(obj, do_unlink=True)

imported = [o for o in imported if o.name in bpy.data.objects]

root = bpy.data.objects.new("TravelerAssetRoot", None)
bpy.context.collection.objects.link(root)
for obj in imported:
    if obj.parent is None:
        obj.parent = root

bpy.context.view_layer.update()

def world_bounds(objects):
    pts = []
    for obj in objects:
        if obj.type == "MESH":
            pts.extend(obj.matrix_world @ Vector(c) for c in obj.bound_box)
    if not pts:
        raise RuntimeError("No mesh geometry in humanoid source")
    mn = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    mx = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return mn, mx

mn, mx = world_bounds(imported)
src_height = mx.z - mn.z
if src_height <= 1e-6:
    raise RuntimeError("Invalid humanoid height")

TARGET_HEIGHT = 3.55
factor = TARGET_HEIGHT / src_height
root.scale = (factor, factor, factor)
bpy.context.view_layer.update()

mn, mx = world_bounds(imported)
root.location.x -= (mn.x + mx.x) * 0.5
root.location.y -= (mn.y + mx.y) * 0.5
root.location.z -= mn.z
bpy.context.view_layer.update()

body_candidates = [o for o in imported if o.type == "MESH"]
body = max(body_candidates, key=lambda o: len(o.data.polygons) if o.data else 0)
armature = None
for mod in body.modifiers:
    if mod.type == "ARMATURE" and getattr(mod, "object", None):
        armature = mod.object
        break
if armature is None and body.parent and body.parent.type == "ARMATURE":
    armature = body.parent

print("traveler_body", body.name, "armature", armature.name if armature else None)

# ------------------------------------------------------------
# Materials - intentionally saturated enough to read in Blender
# ------------------------------------------------------------
def make_mat(name, color, roughness=0.7, metallic=0.0):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name=name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = color
        bsdf.inputs["Roughness"].default_value = roughness
        bsdf.inputs["Metallic"].default_value = metallic
    mat.diffuse_color = color
    return mat

skin_mat  = make_mat("Traveler_Skin",   (0.52, 0.24, 0.12, 1.0), 0.60)
shirt_mat = make_mat("Traveler_Shirt",  (0.68, 0.57, 0.39, 1.0), 0.92)
vest_mat  = make_mat("Traveler_Vest",   (0.11, 0.050, 0.025, 1.0), 0.90)
pants_mat = make_mat("Traveler_Pants",  (0.025, 0.020, 0.018, 1.0), 0.94)
boots_mat = make_mat("Traveler_Boots",  (0.13, 0.045, 0.015, 1.0), 0.78)
sash_mat  = make_mat("Traveler_Sash",   (0.18, 0.060, 0.025, 1.0), 0.88)
strap_mat = make_mat("Traveler_Strap",  (0.08, 0.025, 0.010, 1.0), 0.72)
hair_mat  = make_mat("Traveler_Hair",   (0.018, 0.007, 0.003, 1.0), 0.82)

body.data.materials.clear()
body.data.materials.append(skin_mat)

# ------------------------------------------------------------
# Garment helpers
# ------------------------------------------------------------
group_names = {vg.index: vg.name for vg in body.vertex_groups}

def vertex_has_group(src_vertex, prefixes, min_weight=0.08):
    for g in src_vertex.groups:
        name = group_names.get(g.group, "")
        if any(name == p or name.startswith(p) for p in prefixes) and g.weight >= min_weight:
            return True
    return False

def body_point(local_co):
    return body.matrix_world @ local_co

def duplicate_region(name, prefixes, zmin, zmax, material, clearance, thickness, front_cut=None):
    obj = body.copy()
    obj.data = body.data.copy()
    obj.name = name
    bpy.context.collection.objects.link(obj)

    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.verts.ensure_lookup_table()

    delete = []
    for bv in bm.verts:
        src = body.data.vertices[bv.index]
        p = body_point(src.co)
        keep = zmin <= p.z <= zmax and vertex_has_group(src, prefixes)

        if keep and front_cut is not None:
            front_y, gap_func = front_cut
            if p.y < front_y and abs(p.x) < gap_func(p.z):
                keep = False

        if not keep:
            delete.append(bv)

    bmesh.ops.delete(bm, geom=delete, context="VERTS")
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

    subdiv = obj.modifiers.new("ClothSubdivision", "SUBSURF")
    subdiv.levels = 1
    subdiv.render_levels = 1

    for poly in obj.data.polygons:
        poly.use_smooth = True
    return obj

def section_bounds(z, window=0.05):
    pts = []
    for v in body.data.vertices:
        p = body_point(v.co)
        if abs(p.z - z) <= window:
            pts.append(p)
    if len(pts) < 12:
        all_pts = [body_point(v.co) for v in body.data.vertices]
        pts = sorted(all_pts, key=lambda p: abs(p.z-z))[:96]
    return (
        min(p.x for p in pts), max(p.x for p in pts),
        min(p.y for p in pts), max(p.y for p in pts)
    )

def elliptic_band(name, z0, z1, clearance, material, segments=48):
    levels = [z0, (z0+z1)*0.5, z1]
    verts = []
    faces = []
    for z in levels:
        x0,x1,y0,y1 = section_bounds(z)
        cx = (x0+x1)*0.5
        cy = (y0+y1)*0.5
        rx = (x1-x0)*0.5 + clearance
        ry = (y1-y0)*0.5 + clearance
        for i in range(segments):
            a = 2*math.pi*i/segments
            verts.append((cx+math.cos(a)*rx, cy+math.sin(a)*ry, z))
    for r in range(len(levels)-1):
        for i in range(segments):
            a=r*segments+i
            b=r*segments+(i+1)%segments
            c=(r+1)*segments+(i+1)%segments
            d=(r+1)*segments+i
            faces.append((a,b,c,d))
    mesh=bpy.data.meshes.new(name+"Mesh")
    mesh.from_pydata(verts,[],faces)
    mesh.update()
    obj=bpy.data.objects.new(name,mesh)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(material)
    bev=obj.modifiers.new("SoftEdges","BEVEL")
    bev.width=0.015
    bev.segments=3
    for p in obj.data.polygons:
        p.use_smooth=True
    return obj

def rounded_box(name, loc, dims, material, rot=(0.0,0.0,0.0), bevel=0.03):
    bpy.ops.mesh.primitive_cube_add(location=loc, rotation=rot)
    obj=bpy.context.active_object
    obj.name=name
    obj.dimensions=dims
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(material)
    bev=obj.modifiers.new("SoftEdges","BEVEL")
    bev.width=bevel
    bev.segments=4
    return obj

def curve_strap(name, points, radius, material):
    curve=bpy.data.curves.new(name+"Curve",type="CURVE")
    curve.dimensions="3D"
    curve.bevel_depth=radius
    curve.bevel_resolution=4
    spline=curve.splines.new("BEZIER")
    spline.bezier_points.add(len(points)-1)
    for bp,co in zip(spline.bezier_points,points):
        bp.co=co
        bp.handle_left_type="AUTO"
        bp.handle_right_type="AUTO"
    obj=bpy.data.objects.new(name,curve)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(material)
    return obj

def bone_world(name):
    if armature and name in armature.data.bones:
        b=armature.data.bones[name]
        return armature.matrix_world @ b.head_local, armature.matrix_world @ b.tail_local
    return None

def cone_between(name,p1,p2,r1,r2,material):
    p1,p2=Vector(p1),Vector(p2)
    mid=(p1+p2)*0.5
    vec=p2-p1
    bpy.ops.mesh.primitive_cone_add(vertices=32,radius1=r1,radius2=r2,depth=vec.length,location=mid)
    obj=bpy.context.active_object
    obj.name=name
    obj.rotation_euler=vec.to_track_quat("Z","Y").to_euler()
    obj.data.materials.append(material)
    bev=obj.modifiers.new("SoftEdges","BEVEL")
    bev.width=0.014
    bev.segments=3
    for p in obj.data.polygons:
        p.use_smooth=True
    return obj

# ------------------------------------------------------------
# Outfit - separate, fitted pieces
# ------------------------------------------------------------
# Shirt: fitted body-derived shell including sleeves.
shirt = duplicate_region(
    "Traveler_Shirt",
    ("spine","shoulder","upper_arm","forearm"),
    1.18, 2.98,
    shirt_mat,
    clearance=0.035,
    thickness=0.020,
)

# Vest: body-derived shell but with an intentionally open front.
front_plane = -0.16
vest_gap = lambda z: max(0.075, 0.08 + max(0.0, z-2.15)*0.20)
vest = duplicate_region(
    "Traveler_Vest",
    ("spine","shoulder"),
    1.46, 2.84,
    vest_mat,
    clearance=0.070,
    thickness=0.025,
    front_cut=(front_plane, vest_gap),
)

# Loose pants copied from legs; top/bottom seams are hidden by sash/boots.
pants = duplicate_region(
    "Traveler_Pants",
    ("pelvis","thigh","shin"),
    0.46, 1.80,
    pants_mat,
    clearance=0.055,
    thickness=0.025,
)

# Wide wrapped sash follows the body section instead of intersecting it.
sash = elliptic_band("Traveler_Sash", 1.57, 1.78, 0.075, sash_mat)
rounded_box("Traveler_SashTail_A",(0.10,-0.34,1.36),(0.13,0.045,0.48),sash_mat,rot=(math.radians(4),0,math.radians(8)),bevel=0.016)
rounded_box("Traveler_SashTail_B",(-0.02,-0.34,1.32),(0.11,0.042,0.42),sash_mat,rot=(math.radians(-3),0,math.radians(-7)),bevel=0.016)

# High boots: shafts follow the lower legs, feet are real shoe-shaped blocks.
for side, sign in (("L",-1),("R",1)):
    shin=bone_world(f"shin.{side}")
    if shin:
        ankle=shin[1]
        top=ankle+Vector((0,0,0.58))
        x=ankle.x
    else:
        x=0.17*sign
        ankle=Vector((x,0,0.10))
        top=Vector((x,0,0.68))
    cone_between(f"Traveler_BootShaft_{side}",ankle+Vector((0,0,0.08)),top,0.18,0.17,boots_mat)
    rounded_box(f"Traveler_BootFoot_{side}",(x,-0.12,0.105),(0.34,0.50,0.22),boots_mat,bevel=0.055)

# Thin leather strap across chest.
curve_strap(
    "Traveler_CrossBodyStrap",
    [(-0.30,-0.39,2.73),(-0.13,-0.42,2.38),(0.05,-0.42,2.02),(0.24,-0.37,1.70)],
    0.026,
    strap_mat,
)

# Hair only after clothing is stable: compact cap + sides, never blocking face.
bpy.ops.mesh.primitive_uv_sphere_add(segments=40,ring_count=20,location=(0.0,0.055,3.40))
hair=bpy.context.active_object
hair.name="Traveler_HairCap"
hair.scale=(0.31,0.28,0.15)
bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
hair.data.materials.append(hair_mat)

for x,y,z,sc in [
    (-0.22,0.02,3.32,(0.08,0.11,0.18)),
    (0.22,0.02,3.32,(0.08,0.11,0.18)),
    (-0.15,0.10,3.31,(0.10,0.08,0.16)),
    (0.15,0.10,3.31,(0.10,0.08,0.16)),
]:
    bpy.ops.mesh.primitive_uv_sphere_add(segments=24,ring_count=12,location=(x,y,z))
    lock=bpy.context.active_object
    lock.name="Traveler_HairLock"
    lock.scale=sc
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    lock.data.materials.append(hair_mat)

print("traveler_outfit_v5_created", [shirt.name, vest.name, pants.name])

# ------------------------------------------------------------
# Ground / studio / colored preview
# ------------------------------------------------------------
ground_mat=make_mat("Ground",(0.018,0.022,0.020,1.0),0.96)
bpy.ops.mesh.primitive_plane_add(size=14,location=(0,0,0))
ground=bpy.context.active_object
ground.name="Ground"
ground.data.materials.append(ground_mat)

world=scene.world
if world is None:
    world=bpy.data.worlds.new("World")
    scene.world=world
world.use_nodes=True
bg=world.node_tree.nodes.get("Background")
if bg:
    bg.inputs[0].default_value=(0.006,0.009,0.014,1.0)
    bg.inputs[1].default_value=0.18

def look_at(obj,target):
    direction=Vector(target)-obj.location
    obj.rotation_euler=direction.to_track_quat("-Z","Y").to_euler()

# Brighter neutral lighting so material colors are obvious.
bpy.ops.object.light_add(type="AREA",location=(3.0,-4.0,5.2))
key=bpy.context.active_object
key.data.energy=700
key.data.size=4.0
key.data.color=(1.0,0.88,0.72)
look_at(key,(0,0,1.85))

bpy.ops.object.light_add(type="AREA",location=(-3.2,-1.5,3.8))
fill=bpy.context.active_object
fill.data.energy=320
fill.data.size=3.5
fill.data.color=(0.55,0.65,1.0)
look_at(fill,(0,0,1.75))

bpy.ops.object.light_add(type="AREA",location=(0.5,3.7,4.5))
rim=bpy.context.active_object
rim.data.energy=420
rim.data.size=2.8
rim.data.color=(0.28,0.48,1.0)
look_at(rim,(0,0,2.05))

# Render front/side/back for automatic inspection.
bpy.ops.object.camera_add(location=(0,-6.6,2.05))
cam=bpy.context.active_object
cam.name="Camera"
cam.data.lens=58
scene.camera=cam
target=(0,0,1.78)

views=[
    ("front",(0,-6.6,2.05)),
    ("side",(5.7,0,2.05)),
    ("back",(0,6.6,2.05)),
]
for suffix,loc in views:
    cam.location=loc
    look_at(cam,target)
    scene.render.filepath=str(OUTPUT_DIR/f"traveler_outfit_{suffix}.png")
    bpy.ops.render.render(write_still=True)

# Keep the front view as the default.
cam.location=(0,-6.6,2.05)
look_at(cam,target)

# Force visible Blender viewport into colored material mode for the user.
for window in bpy.context.window_manager.windows:
    for area in window.screen.areas:
        if area.type=="VIEW_3D":
            area.spaces.active.shading.type="MATERIAL"
            area.spaces.active.shading.color_type="MATERIAL"

blend_path=OUTPUT_DIR/"traveler_character_outfit.blend"
bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
print("traveler_outfit_v5_done", blend_path)
