"""No-GPU room preview: projected colored triangles, not a physical renderer.
Does not execute Blender, arbitrary external commands or scripts from the GLB.
"""
import json
import math
import pathlib
import re


def render_previews(model_glb, views_json, output_dir, width=960, height=720):
    import numpy as np
    import trimesh
    from PIL import Image,ImageDraw,ImageFont
    model=pathlib.Path(model_glb).expanduser().resolve()
    vf=pathlib.Path(views_json).expanduser().resolve()
    if not model.is_file() or model.suffix.lower()!='.glb' or model.stat().st_size>100*1024*1024:
        raise ValueError('Arquivo GLB inexistente ou inválido (máx. 100 MB).')
    if not vf.is_file() or vf.suffix.lower()!='.json' or vf.stat().st_size>100000:
        raise ValueError('Arquivo JSON de vistas inválido.')
    if type(width)!=int or type(height)!=int or not 256<=width<=2048 or not 192<=height<=1536:
        raise ValueError('Dimensões da imagem fora da faixa.')
    views=json.loads(vf.read_text(encoding='utf-8'))
    if not isinstance(views,dict) or not 1<=len(views)<=150:raise ValueError('Vistas inválidas.')
    scene=trimesh.load(str(model),force='scene')
    if not scene.geometry:raise ValueError('GLB não contém geometria.')
    combined=[]
    # Preserve the transform graph by using scene.dump() rather than scene.geometry alone.
    for mesh in scene.dump():
        if not isinstance(mesh,trimesh.Trimesh) or len(mesh.faces)==0:continue
        if len(mesh.faces)>50000:raise ValueError('Malha com excesso de faces.')
        verts=np.asarray(mesh.vertices)
        if not np.isfinite(verts).all():raise ValueError('Malha com coordenadas não finitas.')
        colors=np.asarray(mesh.visual.face_colors)[:,:3]
        for f,c in zip(mesh.faces,colors):
            combined.append((verts[f],c))
    if len(combined)>65000:raise ValueError('Modelo com excesso de polígonos para preview CPU.')
    dest=pathlib.Path(output_dir).expanduser().resolve();dest.mkdir(parents=True,exist_ok=True)
    outputs=[]
    for i,(rid,view) in enumerate(views.items()):
        if not re.fullmatch(r'[\w-]{1,70}',str(rid),flags=re.UNICODE):raise ValueError('ID de cômodo inválido.')
        eye=np.array(view['camera_m'],dtype=float);aim=np.array(view['target_m'],dtype=float)
        if eye.shape!=(3,) or aim.shape!=(3,) or not np.isfinite(eye).all() or not np.isfinite(aim).all():
            raise ValueError('Câmera inválida.')
        forward=aim-eye;forward/=max(np.linalg.norm(forward),1e-8)
        right=np.cross(forward,np.array([0.,0.,1.]))
        if np.linalg.norm(right)<.01:right=np.array([1.,0.,0.])
        right/=np.linalg.norm(right)
        up=np.cross(right,forward)
        image=Image.new('RGB',(width,height),(235,238,240))
        draw=ImageDraw.Draw(image)
        fov=math.tan(math.radians(100)/2)
        triangles=[]
        for vertices,rgb in combined:
            rel=vertices-eye
            depths=rel @forward
            if np.min(depths)<.12:continue  # Clip triangles crossing near plane safely.
            xs=(rel@right)/depths;ys=(rel@up)/depths
            points=[(width/2+width*.5*x/fov,height/2-height*.5*y/fov) for x,y in zip(xs,ys)]
            if any(not math.isfinite(q) or abs(q)>40000 for point in points for q in point):continue
            # Painter ordering is an approximation, does not guarantee occlusion correctness.
            diff=np.cross(vertices[1]-vertices[0],vertices[2]-vertices[0]);norm=np.linalg.norm(diff)
            brightness=.72+.22*abs(diff[2])/norm if norm>1e-8 else .8
            color=tuple(int(max(0,min(255,v*brightness))) for v in rgb)
            triangles.append((float(np.mean(depths)),points,color))
        for depth,poly,color in sorted(triangles,key=lambda x:-x[0]):
            draw.polygon(poly,fill=color)
            draw.line(poly+[poly[0]],fill=tuple(int(v*.8) for v in color),width=1)
        # Clear provenance overlay so previews cannot be confused with architectural photos.
        draw.rectangle((0,height-42,width,height),fill=(26,30,36))
        draw.text((12,height-30),f'{view.get("name",rid)[:48]}  |  PREVIEW GEOMÉTRICO  |  NÃO FOTORREALISTA',fill=(255,255,255))
        outfile=dest/('comodo_'+rid+'.png');image.save(outfile);outputs.append(str(outfile))
    return {'ok':True,'pngs':outputs,'renderer':'CPU preview (not photorealistic)',
            'warning':'Pintura aproximada por faces; não prova visibilidade, iluminação real, nem acabamento arquitetônico.'}
