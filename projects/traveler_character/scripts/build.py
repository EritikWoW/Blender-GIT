import bpy
import bmesh
import math
import zipfile
from mathutils import Vector

MODELS_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ---------- source humanoid ----------
blend_files = sorted(MODELS_DIR.rglob("*.blend"))
if not blend_files:
    for archive in sorted(MODELS_DIR.glob("*.zip")):
        extract_dir = MODELS_DIR / archive.stem
        extract_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive, "r") as zf:
            zf.extractall(extract_dir)
    blend_files = sorted(MODELS_DIR.rglob("*.blend"))
if not blend_files:
    raise RuntimeError("No humanoid .blend asset found")

source_blend = blend_files[0]
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)

scene = bpy.context.scene
scene.render.engine = "BLENDER_EEVEE"
scene.render.resolution_x = 900
scene.render.resolution_y = 1200
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.view_settings.exposure = -0.35

with bpy.data.libraries.load(str(source_blend), link=False) as (data_from, data_to):
    data_to.objects = list(data_from.objects)

imported = [o for o in data_to.objects if o is not None]
for obj in imported:
    try:
        bpy.context.collection.objects.link(obj)
    except RuntimeError:
        pass

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
    mn = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    mx = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return mn, mx

mn, mx = world_bounds(imported)
factor = 3.55 / max(mx.z - mn.z, 1e-6)
root.scale = (factor, factor, factor)
bpy.context.view_layer.update()
mn, mx = world_bounds(imported)
root.location.x -= (mn.x + mx.x) * 0.5
root.location.y -= (mn.y + mx.y) * 0.5
root.location.z -= mn.z
bpy.context.view_layer.update()

body = max([o for o in imported if o.type == "MESH"], key=lambda o: len(o.data.polygons))
armature = None
for mod in body.modifiers:
    if mod.type == "ARMATURE" and getattr(mod, "object", None):
        armature = mod.object
        break
if armature is None and body.parent and body.parent.type == "ARMATURE":
    armature = body.parent

print("traveler_body", body.name, "armature", armature.name if armature else None)

# ---------- materials ----------
def principled_node(mat):
    if not mat.use_nodes or not mat.node_tree:
        return None
    for node in mat.node_tree.nodes:
        if node.type == "BSDF_PRINCIPLED":
            return node
    return None

def make_mat(name, rgba, roughness=0.7, metallic=0.0):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name=name)
    mat.use_nodes = True
    mat.diffuse_color = rgba
    bsdf = principled_node(mat)
    if bsdf:
        if "Base Color" in bsdf.inputs:
            bsdf.inputs["Base Color"].default_value = rgba
        if "Roughness" in bsdf.inputs:
            bsdf.inputs["Roughness"].default_value = roughness
        if "Metallic" in bsdf.inputs:
            bsdf.inputs["Metallic"].default_value = metallic
    return mat

skin_mat  = make_mat("Traveler_Skin",  (0.48,0.22,0.11,1),0.62)
shirt_mat = make_mat("Traveler_Shirt", (0.72,0.60,0.40,1),0.92)
vest_mat  = make_mat("Traveler_Vest",  (0.11,0.045,0.018,1),0.90)
pants_mat = make_mat("Traveler_Pants", (0.035,0.028,0.024,1),0.95)
boots_mat = make_mat("Traveler_Boots", (0.16,0.055,0.018,1),0.80)
sash_mat  = make_mat("Traveler_Sash",  (0.21,0.070,0.025,1),0.88)
strap_mat = make_mat("Traveler_Strap", (0.075,0.022,0.008,1),0.74)
ground_mat= make_mat("Ground",         (0.018,0.022,0.020,1),0.98)

body.data.materials.clear()
body.data.materials.append(skin_mat)

# ---------- body data helpers ----------
group_names = {vg.index: vg.name for vg in body.vertex_groups}

def has_group(v, prefixes, min_weight=0.08):
    for g in v.groups:
        n = group_names.get(g.group, "")
        if any(n == p or n.startswith(p) for p in prefixes) and g.weight >= min_weight:
            return True
    return False

def wpos(co):
    return body.matrix_world @ co

def shell_from_body(name, prefixes, zmin, zmax, mat, clearance, thickness, front_v_cut=False):
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
        p = wpos(src.co)
        keep = zmin <= p.z <= zmax and has_group(src, prefixes)
        if keep and front_v_cut and p.y < -0.13 and p.z > 2.48:
            # V neck only, narrow at bottom and wider toward collar
            gap = 0.025 + (p.z - 2.48) * 0.26
            if abs(p.x) < gap:
                keep = False
        if not keep:
            delete.append(bv)

    bmesh.ops.delete(bm, geom=delete, context="VERTS")
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()

    obj.data.materials.clear()
    obj.data.materials.append(mat)

    shrink = obj.modifiers.new("FitToBody","SHRINKWRAP")
    shrink.target = body
    shrink.wrap_method = "NEAREST_SURFACEPOINT"
    shrink.wrap_mode = "OUTSIDE"
    shrink.offset = clearance

    solid = obj.modifiers.new("Thickness","SOLIDIFY")
    solid.thickness = thickness
    solid.offset = 1.0

    for poly in obj.data.polygons:
        poly.use_smooth = True
    return obj

def bone_world(name):
    if armature and name in armature.data.bones:
        b = armature.data.bones[name]
        return armature.matrix_world @ b.head_local, armature.matrix_world @ b.tail_local
    return None

def rounded_box(name, loc, dims, mat, rot=(0,0,0), bevel=0.025):
    bpy.ops.mesh.primitive_cube_add(location=loc, rotation=rot)
    o = bpy.context.active_object
    o.name = name
    o.dimensions = dims
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    o.data.materials.append(mat)
    bev = o.modifiers.new("SoftEdges","BEVEL")
    bev.width = bevel
    bev.segments = 4
    return o

def cone_between(name, p1, p2, r1, r2, mat):
    p1,p2 = Vector(p1),Vector(p2)
    mid=(p1+p2)*0.5
    vec=p2-p1
    bpy.ops.mesh.primitive_cone_add(vertices=36,radius1=r1,radius2=r2,depth=vec.length,location=mid)
    o=bpy.context.active_object
    o.name=name
    o.rotation_euler=vec.to_track_quat("Z","Y").to_euler()
    o.data.materials.append(mat)
    bev=o.modifiers.new("SoftEdges","BEVEL")
    bev.width=0.016
    bev.segments=3
    for p in o.data.polygons:
        p.use_smooth=True
    return o

def section_bounds(z, window=0.05):
    pts=[wpos(v.co) for v in body.data.vertices if abs(wpos(v.co).z-z)<=window]
    if len(pts)<12:
        pts=sorted([wpos(v.co) for v in body.data.vertices],key=lambda p:abs(p.z-z))[:96]
    return min(p.x for p in pts),max(p.x for p in pts),min(p.y for p in pts),max(p.y for p in pts)

def elliptic_band(name,z0,z1,clearance,mat,segments=48):
    levels=[z0,(z0+z1)*0.5,z1]
    verts=[]; faces=[]
    for z in levels:
        x0,x1,y0,y1=section_bounds(z)
        cx=(x0+x1)*0.5; cy=(y0+y1)*0.5
        rx=(x1-x0)*0.5+clearance; ry=(y1-y0)*0.5+clearance
        for i in range(segments):
            a=2*math.pi*i/segments
            verts.append((cx+math.cos(a)*rx,cy+math.sin(a)*ry,z))
    for r in range(2):
        for i in range(segments):
            a=r*segments+i; b=r*segments+(i+1)%segments
            c=(r+1)*segments+(i+1)%segments; d=(r+1)*segments+i
            faces.append((a,b,c,d))
    mesh=bpy.data.meshes.new(name+"Mesh")
    mesh.from_pydata(verts,[],faces); mesh.update()
    o=bpy.data.objects.new(name,mesh); bpy.context.collection.objects.link(o)
    o.data.materials.append(mat)
    bev=o.modifiers.new("SoftEdges","BEVEL"); bev.width=0.014; bev.segments=3
    for p in o.data.polygons:p.use_smooth=True
    return o

def panel_grid(name,x0,x1,z0,z1,y,mat,front=True,nx=8,nz=16):
    verts=[]; faces=[]
    for iz in range(nz+1):
        z=z0+(z1-z0)*iz/nz
        for ix in range(nx+1):
            x=x0+(x1-x0)*ix/nx
            verts.append((x,y,z))
    for iz in range(nz):
        for ix in range(nx):
            a=iz*(nx+1)+ix
            faces.append((a,a+1,a+1+(nx+1),a+(nx+1)))
    mesh=bpy.data.meshes.new(name+"Mesh")
    mesh.from_pydata(verts,[],faces); mesh.update()
    o=bpy.data.objects.new(name,mesh); bpy.context.collection.objects.link(o)
    o.data.materials.append(mat)
    shrink=o.modifiers.new("FitToBody","SHRINKWRAP")
    shrink.target=body
    shrink.wrap_method="NEAREST_SURFACEPOINT"
    shrink.wrap_mode="OUTSIDE"
    shrink.offset=0.065
    solid=o.modifiers.new("Thickness","SOLIDIFY")
    solid.thickness=0.022
    solid.offset=1.0
    sub=o.modifiers.new("Smooth","SUBSURF")
    sub.levels=1; sub.render_levels=1
    return o

def curve_strap(name,points,radius,mat):
    curve=bpy.data.curves.new(name+"Curve",type="CURVE")
    curve.dimensions="3D"; curve.bevel_depth=radius; curve.bevel_resolution=4
    spl=curve.splines.new("BEZIER"); spl.bezier_points.add(len(points)-1)
    for bp,co in zip(spl.bezier_points,points):
        bp.co=co; bp.handle_left_type="AUTO"; bp.handle_right_type="AUTO"
    o=bpy.data.objects.new(name,curve); bpy.context.collection.objects.link(o)
    o.data.materials.append(mat)
    return o

# ---------- outfit ----------
# Shirt: torso and sleeves conform to the original anatomy but remain a separate cloth shell.
shirt_torso = shell_from_body(
    "Traveler_ShirtTorso",
    ("spine","shoulder"),
    1.28,2.96,
    shirt_mat,0.040,0.020,
    front_v_cut=True
)
shirt_arms = shell_from_body(
    "Traveler_ShirtSleeves",
    ("upper_arm","forearm"),
    1.18,2.82,
    shirt_mat,0.045,0.020
)

shirt_yoke = shell_from_body(
    "Traveler_ShirtYoke",
    ("shoulder",),
    2.45,2.98,
    shirt_mat,0.045,0.020
)

# Rolled sleeve cuffs.
for side in ("L","R"):
    fore=bone_world(f"forearm.{side}")
    if fore:
        elbow,wrist=fore
        p=wrist.lerp(elbow,0.20)
        axis=(elbow-wrist).normalized()
        cone_between(f"Traveler_Cuff_{side}",p-axis*0.055,p+axis*0.055,0.145,0.145,shirt_mat)

# Vest: fitted body shell with a clean open center, not flat boards.
vest = shell_from_body(
    "Traveler_Vest",
    ("spine","shoulder"),
    1.46,2.82,
    vest_mat,0.065,0.024,
    front_v_cut=False
)

# Cut a vertical opening through the front half of the vest.
rounded_box("Traveler_VestCutter",(0.0,-0.32,2.14),(0.17,0.58,1.38),ground_mat,bevel=0.0)
vest_cutter=bpy.context.active_object
vest_cutter.hide_render=True
bool_mod=vest.modifiers.new("OpenFront","BOOLEAN")
bool_mod.operation="DIFFERENCE"
bool_mod.solver="EXACT"
bool_mod.object=vest_cutter

# Add a shallow V at the collar using two angled cutters.
for idx,(x,ang) in enumerate(((-0.08,34),(0.08,-34))):
    rounded_box(f"Traveler_VestNeckCutter_{idx}",(x,-0.31,2.69),(0.16,0.55,0.58),ground_mat,rot=(0,math.radians(ang),0),bevel=0.0)
    cutter=bpy.context.active_object
    cutter.hide_render=True
    bm=vest.modifiers.new(f"NeckCut_{idx}","BOOLEAN")
    bm.operation="DIFFERENCE"
    bm.solver="EXACT"
    bm.object=cutter

# Pants: 2-segment loose trousers on each leg.
for side in ("L","R"):
    thigh=bone_world(f"thigh.{side}")
    shin=bone_world(f"shin.{side}")
    if thigh and shin:
        hip,knee=thigh
        knee2,ankle=shin
        cone_between(f"Traveler_PantsUpper_{side}",hip+Vector((0,0,0.03)),knee+Vector((0,0,0.02)),0.245,0.205,pants_mat)
        cone_between(f"Traveler_PantsLower_{side}",knee2+Vector((0,0,0.03)),ankle+Vector((0,0,0.13)),0.205,0.165,pants_mat)

# Waist wrap hides joins and matches the reference silhouette.
elliptic_band("Traveler_Sash",1.57,1.78,0.075,sash_mat)
rounded_box("Traveler_SashTail_A",(0.11,-0.34,1.38),(0.13,0.045,0.48),sash_mat,rot=(math.radians(4),0,math.radians(8)),bevel=0.016)
rounded_box("Traveler_SashTail_B",(-0.02,-0.34,1.34),(0.11,0.042,0.42),sash_mat,rot=(math.radians(-3),0,math.radians(-7)),bevel=0.016)

# Boots: tall leather shafts + separate shoe bodies.
for side,sign in (("L",-1),("R",1)):
    shin=bone_world(f"shin.{side}")
    x=0.17*sign
    if shin:
        knee,ankle=shin
        x=ankle.x
        top=ankle.lerp(knee,0.45)
    else:
        ankle=Vector((x,0,0.10)); top=Vector((x,0,0.72))
    cone_between(f"Traveler_BootShaft_{side}",ankle+Vector((0,0,0.06)),top,0.185,0.17,boots_mat)
    rounded_box(f"Traveler_BootFoot_{side}",(x,-0.13,0.105),(0.34,0.52,0.22),boots_mat,bevel=0.055)

# Cross-body strap.
curve_strap(
    "Traveler_CrossBodyStrap",
    [(-0.29,-0.39,2.72),(-0.13,-0.41,2.38),(0.05,-0.41,2.05),(0.23,-0.37,1.74)],
    0.022,strap_mat
)

print("traveler_outfit_v6_created")

# ---------- studio ----------
bpy.ops.mesh.primitive_plane_add(size=14,location=(0,0,0))
ground=bpy.context.active_object; ground.name="Ground"; ground.data.materials.append(ground_mat)

world=scene.world or bpy.data.worlds.new("World")
scene.world=world; world.use_nodes=True
bg=world.node_tree.nodes.get("Background")
if bg:
    bg.inputs[0].default_value=(0.006,0.008,0.012,1)
    bg.inputs[1].default_value=0.12

def look_at(obj,target):
    obj.rotation_euler=(Vector(target)-obj.location).to_track_quat("-Z","Y").to_euler()

bpy.ops.object.light_add(type="AREA",location=(3.0,-4.2,5.0))
key=bpy.context.active_object; key.data.energy=120; key.data.size=4.0; key.data.color=(1.0,0.90,0.78); look_at(key,(0,0,1.8))
bpy.ops.object.light_add(type="AREA",location=(-3.2,-1.0,3.8))
fill=bpy.context.active_object; fill.data.energy=45; fill.data.size=3.5; fill.data.color=(0.42,0.55,1.0); look_at(fill,(0,0,1.75))
bpy.ops.object.light_add(type="AREA",location=(0.5,3.7,4.5))
rim=bpy.context.active_object; rim.data.energy=70; rim.data.size=2.8; rim.data.color=(0.25,0.45,1.0); look_at(rim,(0,0,2.0))

bpy.ops.object.camera_add(location=(0,-6.6,2.02))
cam=bpy.context.active_object; cam.name="Camera"; cam.data.lens=58; scene.camera=cam
target=(0,0,1.78)
for suffix,loc in [("front",(0,-6.6,2.02)),("side",(5.7,0,2.02)),("back",(0,6.6,2.02))]:
    cam.location=loc; look_at(cam,target)
    scene.render.filepath=str(OUTPUT_DIR/f"traveler_outfit_{suffix}.png")
    bpy.ops.render.render(write_still=True)

cam.location=(0,-6.6,2.02); look_at(cam,target)

for window in bpy.context.window_manager.windows:
    for area in window.screen.areas:
        if area.type=="VIEW_3D":
            area.spaces.active.shading.type="MATERIAL"
            area.spaces.active.shading.color_type="MATERIAL"

blend_path=OUTPUT_DIR/"traveler_character_outfit.blend"
bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
print("traveler_outfit_v6_done",blend_path)
