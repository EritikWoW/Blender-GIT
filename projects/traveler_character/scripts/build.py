import bpy
import math
from mathutils import Vector

bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)

scene = bpy.context.scene
scene.render.engine = 'BLENDER_EEVEE'
scene.render.resolution_x = 800
scene.render.resolution_y = 1000
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = 'PNG'
scene.view_settings.exposure = -0.15

def mat(name, color, rough=0.5, metallic=0.0):
    m = bpy.data.materials.new(name=name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes.get('Principled BSDF')
    if bsdf:
        bsdf.inputs['Base Color'].default_value = color
        bsdf.inputs['Roughness'].default_value = rough
        bsdf.inputs['Metallic'].default_value = metallic
    return m

def cube(name, loc, scale, material, bevel=0.06):
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

def sphere(name, loc, scale, material, segments=32):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segments, ring_count=max(12, segments//2), location=loc)
    o = bpy.context.active_object
    o.name = name
    o.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if material:
        o.data.materials.append(material)
    return o

def cylinder(name, loc, radius, depth, material, rotation=(0,0,0), vertices=24):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth, location=loc, rotation=rotation)
    o = bpy.context.active_object
    o.name = name
    if material:
        o.data.materials.append(material)
    return o

def look_at(obj, target):
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()

skin = mat('Skin', (0.48, 0.16, 0.07, 1.0), 0.56)
skin_hi = mat('SkinHighlight', (0.72, 0.33, 0.12, 1.0), 0.50)
hair = mat('Hair', (0.006, 0.004, 0.003, 1.0), 0.78)
linen = mat('LinenShirt', (0.42, 0.28, 0.13, 1.0), 0.88)
linen_edge = mat('LinenEdge', (0.16, 0.07, 0.025, 1.0), 0.84)
cloak = mat('DarkCloak', (0.012, 0.045, 0.16, 1.0), 0.90)
cloak_edge = mat('CloakEdge', (0.02, 0.09, 0.28, 1.0), 0.86)
trousers = mat('Trousers', (0.018, 0.024, 0.035, 1.0), 0.88)
leather = mat('Leather', (0.12, 0.028, 0.008, 1.0), 0.68)
metal = mat('Buckle', (0.28, 0.15, 0.045, 1.0), 0.30, 0.55)
eye = mat('Eyes', (0.006, 0.008, 0.006, 1.0), 0.3)
ground_mat = mat('GroundMat', (0.012, 0.020, 0.013, 1.0), 1.0)
staff_mat = mat('StaffWood', (0.11, 0.03, 0.006, 1.0), 0.84)
stone_mat = mat('Stone', (0.035, 0.040, 0.032, 1.0), 1.0)

root = bpy.data.objects.new('TravelerRoot', None)
bpy.context.collection.objects.link(root)

torso = cube('Torso', (0, 0, 2.45), (0.54, 0.29, 0.74), linen, 0.10)
hips = cube('Hips', (0, 0, 1.72), (0.43, 0.26, 0.30), trousers, 0.08)

neck = cylinder('Neck', (0, 0, 3.16), 0.14, 0.28, skin)
head = sphere('Head', (0, -0.01, 3.60), (0.32, 0.30, 0.41), skin)
sphere('Nose', (0, -0.312, 3.58), (0.062, 0.075, 0.10), skin_hi, 24)

for x in (-0.105, 0.105):
    sphere('Eye', (x, -0.294, 3.66), (0.034, 0.019, 0.027), eye, 20)

# hair with visible forehead
sphere('HairCap', (0, 0.035, 3.84), (0.37, 0.33, 0.20), hair)
cube('HairSideL', (-0.285, 0.045, 3.64), (0.065, 0.17, 0.22), hair, 0.04)
cube('HairSideR', (0.285, 0.045, 3.64), (0.065, 0.17, 0.22), hair, 0.04)
# compact beard and moustache
sphere('Beard', (0, 0.005, 3.39), (0.27, 0.27, 0.17), hair, 28)
cube('Moustache', (0, -0.298, 3.51), (0.16, 0.022, 0.035), hair, 0.025)

# legs and boots
cylinder('LegL', (-0.20, 0, 1.08), 0.16, 1.20, trousers)
cylinder('LegR', (0.20, 0, 1.08), 0.16, 1.20, trousers)
cube('BootL', (-0.20, -0.08, 0.42), (0.20, 0.31, 0.19), leather, 0.07)
cube('BootR', (0.20, -0.08, 0.42), (0.20, 0.31, 0.19), leather, 0.07)

# arms slightly asymmetric
arm_l = cylinder('ArmL', (-0.61, 0.01, 2.43), 0.145, 1.20, linen, rotation=(0, math.radians(8), math.radians(-3)))
arm_r = cylinder('ArmR', (0.62, 0.01, 2.43), 0.145, 1.20, linen, rotation=(0, math.radians(-13), math.radians(3)))
sphere('HandL', (-0.69, -0.01, 1.82), (0.14, 0.12, 0.16), skin)
sphere('HandR', (0.72, -0.01, 1.80), (0.14, 0.12, 0.16), skin)

# belt and buckle
cylinder('Belt', (0, 0, 1.84), 0.50, 0.13, leather, rotation=(math.radians(90), 0, 0))
cube('Buckle', (0, -0.305, 1.84), (0.095, 0.030, 0.085), metal, 0.02)

# shirt neck opening and lacing
cube('CollarL', (-0.12, -0.292, 2.97), (0.055, 0.025, 0.18), linen_edge, 0.02)
cube('CollarR', (0.12, -0.292, 2.97), (0.055, 0.025, 0.18), linen_edge, 0.02)
for i, z in enumerate((2.91, 2.82, 2.73)):
    lace = cube(f'Lace{i}', (0, -0.322, z), (0.15, 0.012, 0.014), leather, 0.008)
    lace.rotation_euler[1] = math.radians(16 if i % 2 == 0 else -16)

# cloak panels
cloak_back = cube('CloakBack', (0, 0.21, 2.28), (0.57, 0.055, 0.98), cloak, 0.07)
cloak_back.rotation_euler[0] = math.radians(-5)
cube('CloakLeft', (-0.53, 0.08, 2.18), (0.13, 0.09, 0.83), cloak_edge, 0.06)
cube('CloakRight', (0.53, 0.08, 2.18), (0.13, 0.09, 0.83), cloak_edge, 0.06)
cube('CloakMantle', (0, 0.10, 3.01), (0.69, 0.11, 0.21), cloak, 0.10)\ncube('ShoulderL', (-0.56, -0.01, 2.90), (0.15, 0.22, 0.12), cloak_edge, 0.06)\ncube('ShoulderR', (0.56, -0.01, 2.90), (0.15, 0.22, 0.12), cloak_edge, 0.06)\ncube('CloakClasp', (0, -0.31, 2.96), (0.085, 0.025, 0.055), metal, 0.02)

# staff
staff = cylinder('Staff', (0.92, 0.03, 1.67), 0.048, 3.40, staff_mat)
staff.rotation_euler[1] = math.radians(-5)
sphere('StaffTop', (0.78, 0.03, 3.35), (0.09, 0.09, 0.12), staff_mat, 20)

for obj in list(bpy.context.scene.objects):
    if obj is not root and obj.type == 'MESH':
        obj.parent = root

# ground
bpy.ops.mesh.primitive_plane_add(size=16, location=(0,0,0))
ground = bpy.context.active_object
ground.name = 'Ground'
ground.data.materials.append(ground_mat)
ground.parent = None

for i, (x,y,s) in enumerate([(-1.8,0.9,0.22),(1.5,1.1,0.18),(-1.1,-0.8,0.15),(1.9,-0.6,0.20)]):
    o = sphere(f'Stone_{i}', (x,y,s*0.55), (s, s*0.8, s*0.55), stone_mat, 20)
    o.parent = None

world = scene.world
if world is None:
    world = bpy.data.worlds.new('World')
    scene.world = world
world.use_nodes = True
bg = world.node_tree.nodes.get('Background')
if bg:
    bg.inputs[0].default_value = (0.004, 0.007, 0.010, 1.0)
    bg.inputs[1].default_value = 0.22

# restrained cinematic lighting
bpy.ops.object.light_add(type='AREA', location=(3.0, -4.0, 5.6))
key = bpy.context.active_object
key.data.energy = 145
key.data.size = 4.0
key.data.color = (1.0, 0.92, 0.82)
look_at(key, (0,0,2.3))

bpy.ops.object.light_add(type='AREA', location=(-3.2, -1.0, 3.8))
fill = bpy.context.active_object
fill.data.energy = 55
fill.data.size = 3.0
fill.data.color = (0.28, 0.42, 1.0)
look_at(fill, (0,0,2.1))

bpy.ops.object.light_add(type='AREA', location=(0.5, 3.6, 4.8))
rim = bpy.context.active_object
rim.data.energy = 110
rim.data.size = 2.3
rim.data.color = (0.12, 0.42, 1.0)
look_at(rim, (0,0,2.7))

bpy.ops.object.light_add(type='POINT', location=(0.0, -2.5, 2.4))
front = bpy.context.active_object
front.data.energy = 20
front.data.color = (1.0, 0.88, 0.74)

bpy.ops.object.camera_add(location=(4.55, -5.85, 3.85))
cam = bpy.context.active_object
cam.name = 'Camera'
cam.data.lens = 72
scene.camera = cam
look_at(cam, (0,0,2.15))

render_path = OUTPUT_DIR / 'traveler_preview.png'
scene.render.filepath = str(render_path)
bpy.ops.render.render(write_still=True)

blend_path = OUTPUT_DIR / 'traveler_character.blend'
bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))

print('traveler_character_v2_done', render_path, blend_path)
