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
hair_mat  = make_mat("Traveler_Hair",  (0.018,0.007,0.003,1),0.82)
ground_mat= make_mat("Ground",         (0.018,0.022,0.020,1),0.98)

def add_surface_bump(mat, scale=8.0, strength=0.18, distance=0.035):
    nt=mat.node_tree
    bsdf=principled_node(mat)
    if not nt or not bsdf or "Normal" not in bsdf.inputs:
        return
    for node in list(nt.nodes):
        if node.name.startswith("TravelerDetail_"):
            nt.nodes.remove(node)
    tex=nt.nodes.new("ShaderNodeTexCoord")
    tex.name="TravelerDetail_TexCoord"
    noise=nt.nodes.new("ShaderNodeTexNoise")
    noise.name="TravelerDetail_Noise"
    noise.inputs["Scale"].default_value=scale
    if "Detail" in noise.inputs:
        noise.inputs["Detail"].default_value=3.0
    bump=nt.nodes.new("ShaderNodeBump")
    bump.name="TravelerDetail_Bump"
    bump.inputs["Strength"].default_value=strength
    bump.inputs["Distance"].default_value=distance
    nt.links.new(tex.outputs["Generated"],noise.inputs["Vector"])
    nt.links.new(noise.outputs["Fac"],bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"],bsdf.inputs["Normal"])

add_surface_bump(shirt_mat,11.0,0.22,0.025)
add_surface_bump(vest_mat,7.0,0.16,0.022)
add_surface_bump(pants_mat,9.0,0.12,0.020)
add_surface_bump(boots_mat,5.0,0.10,0.018)
add_surface_bump(sash_mat,8.0,0.15,0.020)

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

def shell_from_body(name, prefixes, zmin, zmax, mat, clearance, thickness, front_gap_func=None, front_y=-0.12):
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
        if keep and front_gap_func is not None and p.y < front_y:
            gap = max(0.0, float(front_gap_func(p.z)))
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

    smooth = obj.modifiers.new("GarmentSmooth","LAPLACIANSMOOTH")
    smooth.lambda_factor = 0.10
    smooth.iterations = 2

    solid = obj.modifiers.new("Thickness","SOLIDIFY")
    solid.thickness = thickness
    solid.offset = 1.0

    bevel = obj.modifiers.new("GarmentEdgeSoftness","BEVEL")
    bevel.width = 0.008
    bevel.segments = 2

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
    if "Shirt" in name or "Pants" in name:
        sub=o.modifiers.new("ClothSubdivision","SUBSURF")
        sub.levels=1
        sub.render_levels=1
        tex_name=name+"_Wrinkle"
        tex=bpy.data.textures.get(tex_name) or bpy.data.textures.new(tex_name,type="CLOUDS")
        tex.noise_scale=0.14 if "Shirt" in name else 0.20
        disp=o.modifiers.new("ClothWrinkle","DISPLACE")
        disp.texture=tex
        disp.strength=0.014 if "Shirt" in name else 0.018
        disp.mid_level=0.5
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
# Smooth torso-section helper for clean cloth surfaces.
def torso_section(z,window=0.045,x_limit=0.52):
    pts=[]
    for v in body.data.vertices:
        p=wpos(v.co)
        if abs(p.z-z)<=window and abs(p.x)<=x_limit:
            pts.append(p)
    if len(pts)<12:
        candidates=[wpos(v.co) for v in body.data.vertices if abs(wpos(v.co).x)<=x_limit]
        pts=sorted(candidates,key=lambda p:abs(p.z-z))[:96]
    return min(p.x for p in pts),max(p.x for p in pts),min(p.y for p in pts),max(p.y for p in pts)

def torso_arc(name,z_levels,clearance,mat,gap_func,segments=72,thickness=0.020):
    verts=[]; faces=[]
    pts_per=segments+1
    for z in z_levels:
        x0,x1,y0,y1=torso_section(z)
        cx=(x0+x1)*0.5
        cy=(y0+y1)*0.5
        rx=(x1-x0)*0.5+clearance
        ry=(y1-y0)*0.5+clearance
        gap=max(0.0,float(gap_func(z)))
        start=-math.pi/2+gap
        end=3*math.pi/2-gap
        for i in range(pts_per):
            u=i/segments
            ang=start+(end-start)*u
            verts.append((cx+math.cos(ang)*rx,cy+math.sin(ang)*ry,z))
    for r in range(len(z_levels)-1):
        for i in range(segments):
            p0=r*pts_per+i
            p1=p0+1
            p2=(r+1)*pts_per+i+1
            p3=(r+1)*pts_per+i
            faces.append((p0,p1,p2,p3))
    mesh=bpy.data.meshes.new(name+"Mesh")
    mesh.from_pydata(verts,[],faces)
    mesh.update()
    obj=bpy.data.objects.new(name,mesh)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(mat)
    sub=obj.modifiers.new("ClothSubdivision","SUBSURF")
    sub.levels=1
    sub.render_levels=1
    solid=obj.modifiers.new("ClothThickness","SOLIDIFY")
    solid.thickness=thickness
    solid.offset=1.0
    bev=obj.modifiers.new("SoftEdges","BEVEL")
    bev.width=0.010
    bev.segments=3
    for p in obj.data.polygons:
        p.use_smooth=True
    return obj

# Linen shirt: fully closed over the abdomen, open only at the upper chest.
def shirt_gap(z):
    if z<2.58:
        return 0.0
    return min(0.18,(z-2.58)*0.46)

shirt=torso_arc(
    "Traveler_Shirt",
    [1.34,1.50,1.68,1.88,2.08,2.28,2.46,2.62,2.76,2.88],
    0.030,shirt_mat,shirt_gap,segments=72,thickness=0.018
)

# Long loose sleeves overlap the shoulders and stay continuous to the cuffs.
for side in ("L","R"):
    upper=bone_world(f"upper_arm.{side}")
    fore=bone_world(f"forearm.{side}")
    if upper and fore:
        shoulder,elbow=upper
        _,wrist=fore
        vec=(wrist-shoulder).normalized()
        cone_between(
            f"Traveler_ShirtSleeve_{side}",
            shoulder-vec*0.10,
            wrist+vec*0.025,
            0.290,0.150,shirt_mat
        )
        cuff_center=wrist.lerp(elbow,0.14)
        axis=(elbow-wrist).normalized()
        cone_between(
            f"Traveler_Cuff_{side}",
            cuff_center-axis*0.052,
            cuff_center+axis*0.052,
            0.158,0.158,shirt_mat
        )

# Dark sleeveless vest: clearly open at the front with shirt visible between the panels.
def vest_gap(z):
    if z<2.28:
        return 0.48
    return min(0.78,0.48+(z-2.28)*0.60)

vest=torso_arc(
    "Traveler_Vest",
    [1.48,1.62,1.80,2.00,2.20,2.38,2.54,2.68,2.78],
    0.055,vest_mat,vest_gap,segments=72,thickness=0.022
)

# Long side tails of the vest.
rounded_box("Traveler_VestTail_L",(-0.34,0.05,1.45),(0.22,0.18,0.58),vest_mat,rot=(math.radians(2),0,math.radians(-3)),bevel=0.035)
rounded_box("Traveler_VestTail_R",(0.34,0.05,1.45),(0.22,0.18,0.58),vest_mat,rot=(math.radians(2),0,math.radians(3)),bevel=0.035)

# Pants: one continuous baggy tapered tube per leg, tucked into the boots.
for side in ("L","R"):
    thigh=bone_world(f"thigh.{side}")
    shin=bone_world(f"shin.{side}")
    if thigh and shin:
        hip,_=thigh
        _,ankle=shin
        leg_vec=(ankle-hip).normalized()
        cone_between(
            f"Traveler_Pants_{side}",
            hip-leg_vec*0.03,
            ankle+leg_vec*0.11,
            0.375,0.220,pants_mat
        )

# Dark waist bridge joins both trouser legs under the sash.
elliptic_band("Traveler_PantsWaist",1.42,1.62,0.055,pants_mat)

# Wrapped cloth sash: three irregular overlapping bands, no rigid plank.
def wrapped_band(name,z0,z1,clearance,phase):
    levels=[z0,(z0+z1)*0.5,z1]
    segments=64
    verts=[]; faces=[]
    for r,z in enumerate(levels):
        x0,x1,y0,y1=section_bounds(z)
        cx=(x0+x1)*0.5
        cy=(y0+y1)*0.5
        rx=(x1-x0)*0.5+clearance
        ry=(y1-y0)*0.5+clearance
        for i in range(segments):
            a=2*math.pi*i/segments
            zz=z+0.018*math.sin(2.0*a+phase)+0.008*math.sin(5.0*a+phase*0.5)
            verts.append((cx+math.cos(a)*rx,cy+math.sin(a)*ry,zz))
    for r in range(2):
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
    obj.data.materials.append(sash_mat)
    solid=obj.modifiers.new("SashThickness","SOLIDIFY")
    solid.thickness=0.020
    solid.offset=1.0
    bev=obj.modifiers.new("SashSoftness","BEVEL")
    bev.width=0.012
    bev.segments=3
    for p in obj.data.polygons:
        p.use_smooth=True
    return obj

wrapped_band("Traveler_Sash_1",1.55,1.63,0.090,0.2)
wrapped_band("Traveler_Sash_2",1.61,1.69,0.105,1.4)
wrapped_band("Traveler_Sash_3",1.67,1.76,0.095,2.5)

rounded_box(
    "Traveler_SashTail_A",(0.10,-0.34,1.38),(0.12,0.038,0.48),
    sash_mat,rot=(math.radians(5),math.radians(-2),math.radians(9)),bevel=0.018
)
rounded_box(
    "Traveler_SashTail_B",(-0.03,-0.34,1.33),(0.10,0.036,0.42),
    sash_mat,rot=(math.radians(-4),math.radians(2),math.radians(-8)),bevel=0.018
)

# Boots: tall shafts plus a rounded wedge-shaped foot.
def boot_wedge(name,x,mat):
    y_back=0.10
    y_front=-0.42
    z0=0.02
    z_back=0.22
    z_front=0.14
    hw_back=0.18
    hw_front=0.15
    verts=[
        (x-hw_back,y_back,z0),(x+hw_back,y_back,z0),
        (x+hw_front,y_front,z0),(x-hw_front,y_front,z0),
        (x-hw_back,y_back,z_back),(x+hw_back,y_back,z_back),
        (x+hw_front,y_front,z_front),(x-hw_front,y_front,z_front),
    ]
    faces=[
        (0,1,2,3),(4,7,6,5),
        (0,4,5,1),(1,5,6,2),
        (2,6,7,3),(3,7,4,0),
    ]
    mesh=bpy.data.meshes.new(name+"Mesh")
    mesh.from_pydata(verts,[],faces)
    mesh.update()
    obj=bpy.data.objects.new(name,mesh)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(mat)
    bev=obj.modifiers.new("BootRound","BEVEL")
    bev.width=0.055
    bev.segments=5
    sub=obj.modifiers.new("BootSmooth","SUBSURF")
    sub.levels=1
    sub.render_levels=1
    for p in obj.data.polygons:
        p.use_smooth=True
    return obj

for side,sign in (("L",-1),("R",1)):
    shin=bone_world(f"shin.{side}")
    x=0.18*sign
    if shin:
        knee,ankle=shin
        x=ankle.x
        top=ankle.lerp(knee,0.62)
    else:
        ankle=Vector((x,0,0.10))
        top=Vector((x,0,0.70))
    cone_between(
        f"Traveler_BootShaft_{side}",
        ankle+Vector((0,0,0.055)),top,
        0.190,0.170,boots_mat
    )
    boot_wedge(f"Traveler_BootFoot_{side}",x,boots_mat)

# Flat leather cross-body strap, not a round rope.
def flat_strap(name,points,width,mat):
    pts=[Vector(p) for p in points]
    verts=[]; faces=[]
    for i,p in enumerate(pts):
        if i==0:
            tangent=(pts[1]-pts[0]).normalized()
        elif i==len(pts)-1:
            tangent=(pts[-1]-pts[-2]).normalized()
        else:
            tangent=(pts[i+1]-pts[i-1]).normalized()
        side=Vector((1,0,0))
        if abs(tangent.dot(side))>0.90:
            side=Vector((0,0,1))
        side=(side-tangent*tangent.dot(side)).normalized()
        verts.append(tuple(p-side*width*0.5))
        verts.append(tuple(p+side*width*0.5))
    for i in range(len(pts)-1):
        a=i*2
        faces.append((a,a+1,a+3,a+2))
    mesh=bpy.data.meshes.new(name+"Mesh")
    mesh.from_pydata(verts,[],faces)
    mesh.update()
    obj=bpy.data.objects.new(name,mesh)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(mat)
    solid=obj.modifiers.new("StrapThickness","SOLIDIFY")
    solid.thickness=0.018
    solid.offset=0.0
    bev=obj.modifiers.new("StrapEdges","BEVEL")
    bev.width=0.008
    bev.segments=2
    return obj

flat_strap(
    "Traveler_CrossBodyStrap",
    [(-0.30,-0.40,2.73),(-0.14,-0.42,2.40),(0.04,-0.42,2.06),(0.24,-0.37,1.73)],
    0.080,strap_mat
)

# Compact dark hair cap with curved strands, no side-sphere "ears".
bpy.ops.mesh.primitive_uv_sphere_add(segments=48,ring_count=24,location=(0.0,0.045,3.40))
hair=bpy.context.active_object
hair.name="Traveler_Hair"
hair.scale=(0.272,0.238,0.130)
bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)

bm=bmesh.new()
bm.from_mesh(hair.data)
bm.verts.ensure_lookup_table()
delete=[]
for v in bm.verts:
    p=hair.matrix_world @ v.co
    if p.z<3.31 or (p.y<-0.08 and p.z<3.48):
        delete.append(v)
bmesh.ops.delete(bm,geom=delete,context="VERTS")
bm.to_mesh(hair.data)
bm.free()
hair.data.update()
hair.data.materials.append(hair_mat)
solid=hair.modifiers.new("HairThickness","SOLIDIFY")
solid.thickness=0.020
solid.offset=1.0
for p in hair.data.polygons:
    p.use_smooth=True

for i,pts in enumerate([
    [(-0.20,-0.03,3.49),(-0.22,0.01,3.40),(-0.23,0.05,3.31)],
    [(-0.11,-0.05,3.51),(-0.15,0.00,3.42),(-0.17,0.07,3.31)],
    [(0.11,-0.05,3.51),(0.15,0.00,3.42),(0.17,0.07,3.31)],
    [(0.20,-0.03,3.49),(0.22,0.01,3.40),(0.23,0.05,3.31)],
    [(-0.14,0.05,3.52),(-0.16,0.12,3.41),(-0.13,0.17,3.30)],
    [(0.14,0.05,3.52),(0.16,0.12,3.41),(0.13,0.17,3.30)],
]):
    curve_strap(f"Traveler_HairStrand_{i}",pts,0.012,hair_mat)

print("traveler_outfit_v15_created")

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
print("traveler_outfit_v13_done",blend_path)
