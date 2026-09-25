import bpy
import math

bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)

scene = bpy.context.scene
scene.render.engine = 'BLENDER_EEVEE'
scene.render.resolution_x = 800
scene.render.resolution_y = 450
scene.render.resolution_percentage = 100

bpy.ops.mesh.primitive_plane_add(size=10, location=(0, 0, 0))
ground = bpy.context.active_object
ground.name = "Ground"

bpy.ops.mesh.primitive_cube_add(size=2, location=(0, 0, 1))
cube = bpy.context.active_object
cube.name = "MainCube"

mat = bpy.data.materials.new(name="CubeMaterial")
mat.use_nodes = True
bsdf = mat.node_tree.nodes.get("Principled BSDF")
if bsdf:
    bsdf.inputs["Base Color"].default_value = (0.1, 0.5, 0.95, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.35
cube.data.materials.append(mat)

bpy.ops.object.light_add(type='SUN', location=(4, -4, 7))
sun = bpy.context.active_object
sun.data.energy = 2.5
sun.rotation_euler = (math.radians(35), 0, math.radians(25))

bpy.ops.object.light_add(type='AREA', location=(3, -4, 5))
area = bpy.context.active_object
area.data.energy = 900
area.data.size = 4.0

bpy.ops.object.camera_add(location=(6, -6, 4))
cam = bpy.context.active_object
scene.camera = cam

def look_at(obj, target=(0, 0, 1)):
    import mathutils
    direction = mathutils.Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()

look_at(cam)

render_path = OUTPUT_DIR / "preview.png"
scene.render.image_settings.file_format = 'PNG'
scene.render.filepath = str(render_path)
bpy.ops.render.render(write_still=True)

blend_path = OUTPUT_DIR / "scene.blend"
bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))

print("template_project_done", render_path, blend_path)
