"""Blender Cycles scene renderer for audited ArqFiel metric GLB geometry.

Invocation: blender --background --python blender_render.py -- model.glb views.json output samples
Only the geometry and coordinates from GLB drive spatial composition.
Procedural materials/light rigs are illustrative and cannot certify existing finishes.
"""
import bpy
import json
import math
import pathlib
import sys
from mathutils import Vector


def _safe_name(value):
    return ''.join(ch for ch in str(value) if ch.isalnum() or ch in '_-')[:50]


def _build_surface_material(name, rgb, roughness=0.7, metallic=0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get('Principled BSDF')
    if bsdf is not None:
        bsdf.inputs['Base Color'].default_value = tuple(rgb[:3]) + (1,)
        bsdf.inputs['Roughness'].default_value = roughness
        bsdf.inputs['Metallic'].default_value = metallic
    return mat


def _converted_color(obj):
    # Imported GLB vertex colors are preserved. Do not replace source-supplied textures.
    for material in obj.data.materials:
        if material and material.use_nodes:
            node = material.node_tree.nodes.get('Principled BSDF')
            if node:
                return tuple(node.inputs['Base Color'].default_value[:3])
    return (0.79, 0.76, 0.71)


def _prepare_materials():
    for ob in bpy.context.scene.objects:
        if ob.type != 'MESH':
            continue
        if not ob.data.materials:
            ob.data.materials.append(_build_surface_material('ArqFiel-Neutro', (0.78, 0.75, 0.7)))
        # Add subtle edge highlights without changing the exported GLB geometry.
        if ob.name.startswith(('wall:', 'furniture:')):
            bevel = ob.modifiers.new('Cantos suaves – visual', type='BEVEL')
            bevel.width = 0.008
            bevel.segments = 2
            # Default bevel mode preserves all source mesh coordinates.
            normal = ob.modifiers.new('Weighted normals – visual', type='WEIGHTED_NORMAL')
            normal.keep_sharp = True


def _add_area_light(name, position, energy, size):
    ld = bpy.data.lights.new(name, type='AREA')
    ld.energy = energy
    ld.shape = 'DISK'
    ld.size = size
    light = bpy.data.objects.new(name, ld)
    bpy.context.scene.collection.objects.link(light)
    light.location = position
    light.rotation_euler = (0, 0, 0)
    return light


def _configure_engine(scene, samples):
    scene.render.engine = 'CYCLES'
    scene.cycles.samples = int(samples)
    scene.cycles.use_denoising = True
    scene.render.resolution_x = 1600
    scene.render.resolution_y = 1200
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGBA'
    scene.render.film_transparent = False
    scene.render.use_file_extension = True
    scene.camera.data.lens = 20
    try:
        scene.view_settings.view_transform = 'AgX'
    except (TypeError, ValueError):
        scene.view_settings.view_transform = 'Standard'
    try:
        scene.view_settings.look = 'Medium High Contrast'
    except (TypeError, ValueError):
        pass
    scene.view_settings.exposure = 0.0
    scene.view_settings.gamma = 1.0


def main():
    if '--' not in sys.argv:
        raise ValueError('Blender requer argumentos após --.')
    argv = sys.argv[sys.argv.index('--') + 1:]
    if len(argv) != 4:
        raise ValueError('Informe modelo GLB, vistas JSON, diretório e amostras.')
    model, cameras, outdir, sample_text = argv
    samples = int(sample_text)
    if not 16 <= samples <= 1024:
        raise ValueError('Cycles precisa de 16 a 1024 amostras.')
    output = pathlib.Path(outdir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    data = json.loads(pathlib.Path(cameras).read_text(encoding='utf-8'))
    if not isinstance(data, dict) or not 1 <= len(data) <= 150:
        raise ValueError('Nenhuma vista ou quantidade de vistas inválida.')
    for rid, view in data.items():
        if not isinstance(view, dict):
            raise ValueError('Vista malformada: ' + str(rid))
        for prop in ('camera_m', 'target_m'):
            coords = view.get(prop)
            if not isinstance(coords, list) or len(coords) != 3 or not all(
                isinstance(q, (int, float)) and math.isfinite(q) for q in coords
            ):
                raise ValueError('Câmera não validada: ' + str(rid))

    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    bpy.ops.import_scene.gltf(filepath=str(pathlib.Path(model).resolve()))
    _prepare_materials()
    world = bpy.context.scene.world
    if world is None:
        world = bpy.data.worlds.new('ArqFiel – ambiente')
        bpy.context.scene.world = world
    world.use_nodes = True
    background = world.node_tree.nodes.get('Background')
    if background:
        background.inputs['Color'].default_value = (0.65, 0.72, 0.78, 1)
        background.inputs['Strength'].default_value = 0.65

    scene = bpy.context.scene
    camera_data = bpy.data.cameras.new('ArqFiel – interior')
    camera = bpy.data.objects.new('ArqFiel – interior', camera_data)
    scene.collection.objects.link(camera)
    scene.camera = camera
    camera_data.type = 'PERSP'
    _configure_engine(scene, samples)

    results = []
    for n, (rid, view) in enumerate(data.items()):
        eye = Vector(view['camera_m'])
        aim = Vector(view['target_m'])
        direction = aim - eye
        if direction.length < 0.01:
            raise ValueError('Vista sem direção: ' + str(rid))
        camera.location = eye
        camera.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
        room_light = _add_area_light('Luz difusa ' + str(n), Vector((aim.x, aim.y, 2.45)), 650, 3.5)
        fill_light = _add_area_light('Luz de preenchimento ' + str(n), Vector((eye.x, eye.y, 2.30)), 280, 2.0)
        name = _safe_name(rid) or str(n)
        target = output / ('comodo_' + name + '.png')
        scene.render.filepath = str(target)
        bpy.ops.render.render(write_still=True)
        results.append({'room_id': rid, 'file': target.name, 'samples': samples,
                        'camera_m': list(eye), 'target_m': list(aim)})
        bpy.data.objects.remove(room_light, do_unlink=True)
        bpy.data.objects.remove(fill_light, do_unlink=True)
    (output / 'render_manifest.json').write_text(json.dumps({
        'renderer': 'Blender Cycles', 'physically_based': True,
        'geometry_source': 'validated-metric-GLB',
        'photographic_identity_guaranteed': False,
        'finishes_proven': False, 'views': results}, indent=2, ensure_ascii=False), encoding='utf-8')


if __name__ == '__main__':
    main()
