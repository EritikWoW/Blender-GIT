import bpy
import math
from mathutils import Vector

# Clean scene
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)

scene = bpy.context.scene
scene.render.engine = 'BLENDER_EEVEE'
scene.render.resolution_x = 800
scene.render.resolution_y = 1000
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = 'PNG'

# ---------- helpers ----------
def mat(name, color, rough=0.5, metallic=0.0):
    m = bpy.data.materials.new(name=name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes.get('Principled BSDF')
    if bsdf:
        bsdf.inputs['Base Color'].default_value = color
        bsdf.inputs['Roughness'].default_value = rough
        bsdf.inputs['Metallic'].default_value = metallic
    return m

def cube(name, loc, scale, material, bevel=0.08):
    bpy.ops.mesh.primitive_cube_add(location=loc)
    o = bpy.context.active_object
    o.name = name
    o.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if bevel:
        mod = o.modifiers.new('Bevel', 'BEVEL')
        mod.width = bevel
        mod.segments = 3
    if material:
        o.data.materials.append(material)
    return o

def sphere(name, loc, scale, material):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, location=loc)
    o = bpy.context.active_object
    o.name = name
    o.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if material:
        o.data.materials.append(material)
    return o

def cylinder(name, loc, radius, depth, material, rotation=(0,0,0)):
    bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=radius, depth=depth, location=loc, rotation=rotation)
    o = bpy.context.active_object
    o.name = name
    if material:
        o.data.materials.append(material)
    return o

def look_at(obj, target):
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()

# ---------- palette ----------
skin = mat('Skin', (0.58, 0.34, 0.22, 1.0), 0.58)
skin_light = mat('SkinLight', (0.72, 0.48, 0.33, 1.0), 0.55)
hair = mat('Hair', (0.035, 0.022, 0.018, 1.0), 0.8)
linen = mat('LinenShirt', (0.58, 0.50, 0.39, 1.0), 0.9)
cloak = mat('DarkCloak', (0.045, 0.06, 0.07, 1.0), 0.92)
trousers = mat('Trousers', (0.07, 0.075, 0.08, 1.0), 0.86)
leather = mat('Leather', (0.13, 0.055, 0.025, 1.0), 0.72)
metal = mat('Buckle', (0.35, 0.26, 0.12, 1.0), 0.32, 0.55)
eye = mat('Eyes', (0.02, 0.025, 0.02, 1.0), 0.35)
ground_mat = mat('GroundMat', (0.035, 0.045, 0.035, 1.0), 1.0)
staff_mat = mat('StaffWood', (0.17, 0.08, 0.035, 1.0), 0.9)

# ---------- body ----------
root = bpy.data.objects.new('TravelerRoot', None)
bpy.context.collection.objects.link(root)

torso = cube('Torso', (0, 0, 2.45), (0.48, 0.28, 0.72), linen, 0.12)
hips = cube('Hips', (0, 0, 1.72), (0.42, 0.26, 0.30), trousers, 0.10)

neck = cylinder('Neck', (0, 0, 3.16), 0.14, 0.30, skin)
head = sphere('Head', (0, 0, 3.58), (0.36, 0.32, 0.44), skin)

# nose
nose = sphere('Nose', (0, -0.315, 3.58), (0.075, 0.075, 0.12), skin_light)
# eyes
for x in (-0.115, 0.115):
    sphere('Eye', (x, -0.292, 3.66), (0.042, 0.025, 0.035), eye)

# hair cap + side hair
hair_cap = sphere('HairCap', (0, 0.02, 3.86), (0.39, 0.34, 0.23), hair)
cube('HairSideL', (-0.29, 0.02, 3.63), (0.08, 0.20, 0.25), hair, 0.05)
cube('HairSideR', (0.29, 0.02, 3.63), (0.08, 0.20, 0.25), hair, 0.05)
# beard / stubble block
beard = sphere('Beard', (0, -0.02, 3.41), (0.30, 0.29, 0.22), hair)

# legs
leg_l = cylinder('LegL', (-0.20, 0, 1.08), 0.17, 1.20, trousers)
leg_r = cylinder('LegR', (0.20, 0, 1.08), 0.17, 1.20, trousers)

# boots
boot_l = cube('BootL', (-0.20, -0.07, 0.42), (0.20, 0.33, 0.20), leather, 0.08)
boot_r = cube('BootR', (0.20, -0.07, 0.42), (0.20, 0.33, 0.20), leather, 0.08)

# arms
arm_l = cylinder('ArmL', (-0.62, 0.0, 2.42), 0.15, 1.25, linen, rotation=(0, math.radians(7), 0))
arm_r = cylinder('ArmR', (0.62, 0.0, 2.42), 0.15, 1.25, linen, rotation=(0, math.radians(-10), 0))

hand_l = sphere('HandL', (-0.70, 0.0, 1.79), (0.15, 0.13, 0.17), skin)
hand_r = sphere('HandR', (0.72, 0.0, 1.78), (0.15, 0.13, 0.17), skin)

# belt
belt = cylinder('Belt', (0, 0, 1.84), 0.50, 0.16, leather, rotation=(math.radians(90), 0, 0))
buckle = cube('Buckle', (0, -0.305, 1.84), (0.10, 0.035, 0.095), metal, 0.025)

# cloak: back panel + shoulder mantle
cloak_back = cube('CloakBack', (0, 0.18, 2.27), (0.55, 0.06, 0.95), cloak, 0.09)
cloak_back.rotation_euler[0] = math.radians(-4)
mantle = cube('CloakMantle', (0, 0.10, 3.00), (0.62, 0.10, 0.23), cloak, 0.12)

# staff in right hand
staff = cylinder('Staff', (0.92, 0.02, 1.65), 0.055, 3.30, staff_mat)
staff.rotation_euler[1] = math.radians(-4)

# parent character pieces
for obj in list(bpy.context.scene.objects):
    if obj is not root and obj.type in {'MESH'} and obj.name != 'Ground':
        obj.parent = root

# ---------- ground ----------
bpy.ops.mesh.primitive_plane_add(size=16, location=(0,0,0))
ground = bpy.context.active_object
ground.name = 'Ground'
ground.data.materials.append(ground_mat)

# small stones
stone_mat = mat('Stone', (0.09, 0.095, 0.08, 1.0), 1.0)
for i, (x,y,s) in enumerate([(-1.8,0.9,0.22),(1.5,1.1,0.18),(-1.1,-0.8,0.15),(1.9,-0.6,0.20)]):
    o = sphere(f'Stone_{i}', (x,y,s*0.55), (s, s*0.8, s*0.55), stone_mat)

# ---------- lighting ----------
world = scene.world
if world is None:
    world = bpy.data.worlds.new('World')
    scene.world = world
world.use_nodes = True
bg = world.node_tree.nodes.get('Background')
if bg:
    bg.inputs[0].default_value = (0.008, 0.012, 0.018, 1.0)
    bg.inputs[1].default_value = 0.35

bpy.ops.object.light_add(type='AREA', location=(3.2, -4.2, 5.8))
key = bpy.context.active_object
key.data.energy = 1100
key.data.size = 4.0
look_at(key, (0,0,2.2))

bpy.ops.object.light_add(type='AREA', location=(-3.5, -1.2, 3.8))
fill = bpy.context.active_object
fill.data.energy = 500
fill.data.size = 3.0
look_at(fill, (0,0,2.0))

bpy.ops.object.light_add(type='AREA', location=(0.5, 3.8, 4.8))
rim = bpy.context.active_object
rim.data.energy = 900
rim.data.size = 2.5
look_at(rim, (0,0,2.7))

# ---------- camera ----------
bpy.ops.object.camera_add(location=(5.9, -7.4, 4.25))
cam = bpy.context.active_object
cam.name = 'Camera'
cam.data.lens = 58
scene.camera = cam
look_at(cam, (0,0,2.05))

# ---------- render/save ----------
render_path = OUTPUT_DIR / 'traveler_preview.png'
scene.render.filepath = str(render_path)
bpy.ops.render.render(write_still=True)

blend_path = OUTPUT_DIR / 'traveler_character.blend'
bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))

print('traveler_character_done', render_path, blend_path)
