"""Optional Blender headless rendering: executed by the locally installed Blender only.
Invocation: blender -b --python blender_render.py -- model.glb cameras.json output_dir samples
"""
import bpy
import json
import math
import pathlib
import sys
from mathutils import Vector


def main():
    a=sys.argv[sys.argv.index('--')+1:]
    model,cameras,outdir,samples=a
    output=pathlib.Path(outdir)
    data=json.loads(pathlib.Path(cameras).read_text(encoding='utf-8'))
    if not isinstance(data,dict) or len(data)>150:raise ValueError('Vista inválida ou excesso de cômodos.')
    bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
    bpy.ops.import_scene.gltf(filepath=model)
    world=bpy.context.scene.world
    if world is None:world=bpy.data.worlds.new('World');bpy.context.scene.world=world
    world.use_nodes=True
    world.node_tree.nodes.get('Background').inputs['Color'].default_value=(0.8,0.84,0.91,1)
    world.node_tree.nodes.get('Background').inputs['Strength'].default_value=0.7
    scene=bpy.context.scene
    scene.render.engine='CYCLES';scene.cycles.samples=int(samples)
    scene.render.resolution_x=1280;scene.render.resolution_y=960;scene.render.resolution_percentage=100
    scene.render.image_settings.file_format='PNG'
    camera_data=bpy.data.cameras.new('Camera-Comodo');camera=bpy.data.objects.new('Camera-Comodo',camera_data)
    scene.collection.objects.link(camera);scene.camera=camera;camera_data.type='PERSP';camera_data.lens=21
    light_data=bpy.data.lights.new('Iluminacao difusa',type='AREA')
    light=bpy.data.objects.new('Iluminacao difusa',light_data);scene.collection.objects.link(light)
    light_data.energy=1900;light_data.shape='DISK';light_data.size=5.0
    for n,(rid,view) in enumerate(data.items()):
        eye=Vector(view['camera_m']);aim=Vector(view['target_m'])
        camera.location=eye
        direction=aim-eye
        if direction.length<0.01:direction=Vector((1,0,-.1))
        camera.rotation_euler=direction.to_track_quat('-Z','Y').to_euler()
        light.location=(eye+aim)/2+Vector((0,0,2.0))
        safe_name=''.join(c for c in rid if c.isalnum() or c in '_-')[:50] or str(n)
        scene.render.filepath=str(output/('comodo_'+safe_name+'.png'))
        bpy.ops.render.render(write_still=True)


if __name__=='__main__':main()
