"""Deterministic, geometry-first room model builder. Units: meters, Z up.
All source files and embedded text are untrusted data. Never execute them.
"""
import json
import math
import pathlib
import re
import shutil
import subprocess
from itertools import combinations

EPS = 1e-6
MAX_INPUT_BYTES = 40 * 1024 * 1024
HEX = re.compile(r'^#[0-9a-fA-F]{6}$')


def _point(p):
    return (isinstance(p, (tuple, list)) and len(p) == 2 and
            all(isinstance(v, (float, int)) and not isinstance(v, bool) and math.isfinite(v) for v in p))


def _cross(a, b, c):
    return (b[0]-a[0])*(c[1]-a[1]) - (b[1]-a[1])*(c[0]-a[0])


def _area(pts):
    return .5 * sum(pts[i][0]*pts[(i+1)%len(pts)][1] - pts[(i+1)%len(pts)][0]*pts[i][1] for i in range(len(pts)))


def _intersects(a, b, c, d):
    def on(p, q, r):
        return abs(_cross(p,q,r)) < EPS and min(p[0],q[0])-EPS <= r[0] <= max(p[0],q[0])+EPS and min(p[1],q[1])-EPS <= r[1] <= max(p[1],q[1])+EPS
    u,v = _cross(a,b,c), _cross(a,b,d)
    x,y = _cross(c,d,a), _cross(c,d,b)
    if ((u > EPS and v < -EPS) or (u < -EPS and v > EPS)) and ((x > EPS and y < -EPS) or (x < -EPS and y > EPS)):
        return True
    return any((on(a,b,c),on(a,b,d),on(c,d,a),on(c,d,b)))


def _simple_polygon(poly):
    n = len(poly)
    if n < 3 or abs(_area(poly)) < EPS: return False
    if any(math.dist(poly[i],poly[(i+1)%n]) < EPS for i in range(n)): return False
    for i in range(n):
        for j in range(i+1,n):
            if j == i+1 or (i==0 and j==n-1): continue
            if _intersects(poly[i],poly[(i+1)%n],poly[j],poly[(j+1)%n]): return False
    return True


def _inside(point, poly):
    if not _point(point): return False
    x,y = point
    for a,b in zip(poly,poly[1:]+poly[:1]):
        if abs(_cross(a,b,point)) < EPS and min(a[0],b[0])-EPS <= x <= max(a[0],b[0])+EPS and min(a[1],b[1])-EPS <= y <= max(a[1],b[1])+EPS:
            return True
    crossing = False
    for a,b in zip(poly,poly[1:]+poly[:1]):
        if (a[1] > y) != (b[1] > y):
            xhit = a[0]+(y-a[1])*(b[0]-a[0])/(b[1]-a[1])
            if x < xhit: crossing = not crossing
    return crossing



def _strict_inside(point, poly):
    if not _inside(point, poly): return False
    return not any(abs(_cross(a,b,point)) < EPS and
                   min(a[0],b[0])-EPS <= point[0] <= max(a[0],b[0])+EPS and
                   min(a[1],b[1])-EPS <= point[1] <= max(a[1],b[1])+EPS
                   for a,b in zip(poly,poly[1:]+poly[:1]))


def _polys_overlap(first, second):
    # Reject intersections with positive surface area, but allow shared perimeter walls.
    if max(p[0] for p in first)<=min(p[0] for p in second)+EPS or max(p[0] for p in second)<=min(p[0] for p in first)+EPS:
        return False
    if max(p[1] for p in first)<=min(p[1] for p in second)+EPS or max(p[1] for p in second)<=min(p[1] for p in first)+EPS:
        return False
    for a,b in zip(first,first[1:]+first[:1]):
        for c,d in zip(second,second[1:]+second[:1]):
            u,v=_cross(a,b,c),_cross(a,b,d)
            x,y=_cross(c,d,a),_cross(c,d,b)
            if u*v<-EPS and x*y<-EPS: return True
    for source,target in ((first,second),(second,first)):
        if any(_strict_inside(p,target) for p in source): return True
        for a,b,c in _earclip(source):
            center=[sum(source[i][j] for i in (a,b,c))/3 for j in (0,1)]
            if _strict_inside(center,target): return True
    return False


def _wall_covers(a, b, walls):
    ln = math.dist(a,b)
    spans = []
    for w in walls:
        p,q = w['from'], w['to']
        if abs(_cross(a,b,p)) > EPS*max(1,ln) or abs(_cross(a,b,q)) > EPS*max(1,ln): continue
        t1 = ((p[0]-a[0])*(b[0]-a[0])+(p[1]-a[1])*(b[1]-a[1]))/ln**2
        t2 = ((q[0]-a[0])*(b[0]-a[0])+(q[1]-a[1])*(b[1]-a[1]))/ln**2
        lo,hi = max(0,min(t1,t2)), min(1,max(t1,t2))
        if hi>lo: spans.append((lo,hi))
    spans.sort()
    covered=0.0
    for lo,hi in spans:
        if lo>covered+1e-4: return False
        covered=max(covered,hi)
    return covered>=1-1e-4


def validate_project(project):
    errors=[]; warnings=[]
    if not isinstance(project,dict): return {'ok':False,'errors':['Projeto precisa ser um objeto JSON.'],'warnings':[], 'fidelity':'invalid', 'stats':{}}
    info=project.get('project') or {}
    if project.get('schema_version')!='1.0': errors.append('schema_version precisa ser 1.0.')
    if info.get('units')!='m': errors.append('As unidades precisam ser metros (m); converta antes de modelar.')
    rooms=project.get('rooms') or []
    walls=project.get('walls') or []
    furniture=project.get('furniture') or []
    level=project.get('level') or {}
    ceiling=level.get('ceiling_height')
    ceiling_ok=isinstance(ceiling,(float,int)) and not isinstance(ceiling,bool) and math.isfinite(ceiling) and 2.0<=ceiling<=15
    if not ceiling_ok: errors.append('Pé-direito inválido; informar ceiling_height em metros (2–15).')
    if not 1<=len(rooms)<=150: errors.append('Informe de 1 a 150 cômodos.')
    if not 1<=len(walls)<=1500: errors.append('Informe de 1 a 1500 paredes.')
    ids=set(); room_map={}; valid_polys={}
    for r in rooms:
        rid=r.get('id')
        if not isinstance(rid,str) or not rid or rid in ids: errors.append('ID de cômodo ausente ou duplicado.'); continue
        ids.add(rid); room_map[rid]=r
        poly=r.get('polygon') or []
        if not isinstance(poly,list) or not all(_point(p) for p in poly) or not _simple_polygon(poly):
            errors.append(f'Polígono inválido ou autointersectado no cômodo {rid}.')
        else: valid_polys[rid]=poly
        if r.get('floor_color') and not HEX.fullmatch(r['floor_color']): errors.append(f'Cor inválida do piso de {rid}.')
    for (rid_a,pa),(rid_b,pb) in combinations(valid_polys.items(),2):
        if _polys_overlap(pa,pb):errors.append(f'Cômodos sobrepostos: {rid_a} e {rid_b}.')
    wallids=set(); openingids=set()
    for w in walls:
        wid=w.get('id')
        if not isinstance(wid,str) or not wid or wid in wallids: errors.append('ID de parede ausente ou duplicado.'); continue
        wallids.add(wid)
        a,b=w.get('from'),w.get('to'); t=w.get('thickness')
        if not _point(a) or not _point(b) or math.dist(a,b)<EPS: errors.append(f'Parede {wid} sem segmento válido.'); continue
        if not isinstance(t,(float,int)) or not .05<=t<=1.5: errors.append(f'Parede {wid} com espessura inválida (0,05 a 1,5m).')
        length=math.dist(a,b); intervals=[]
        for opening in w.get('openings',[]):
            oid=opening.get('id'); kind=opening.get('kind')
            if not isinstance(oid,str) or not oid or oid in openingids: errors.append(f'Abertura inválida/duplicada na parede {wid}.')
            openingids.add(oid)
            off,width,sill=opening.get('offset'),opening.get('width'),opening.get('sill',0)
            if any(not isinstance(v,(int,float)) or isinstance(v,bool) or not math.isfinite(v) for v in [off,width,sill]): errors.append(f'Abertura {oid} com coordenadas inválidas.');continue
            if off<0 or width<=0 or off+width>length+EPS or sill<0: errors.append(f'Abertura {oid} fora dos limites da parede.');continue
            intervals.append((off,off+width,oid))
            if kind=='arch':
                spring=opening.get('spring_height');rise=opening.get('rise')
                if any(not isinstance(v,(int,float)) for v in [spring,rise]) or spring<.3 or rise<=0 or sill>=spring or (ceiling_ok and spring+rise>ceiling+EPS):
                    errors.append(f'Arco {oid} ultrapassa pé-direito ou tem cotas inválidas.')
            elif kind in ('door','window'):
                height=opening.get('height')
                if not isinstance(height,(int,float)) or height<=0 or (ceiling_ok and sill+height>ceiling+EPS): errors.append(f'Abertura {oid} ultrapassa pé-direito ou tem altura inválida.')
            else: errors.append(f'Tipo de abertura desconhecido {kind} na parede {wid}.')
        intervals.sort()
        for o1,o2 in zip(intervals, intervals[1:]):
            if o2[0]<o1[1]-EPS: errors.append(f'Aberturas sobrepostas na parede {wid}: {o1[2]} e {o2[2]}.')
    for rid,poly in valid_polys.items():
        for a,b in zip(poly,poly[1:]+poly[:1]):
            if not _wall_covers(a,b,[w for w in walls if _point(w.get('from')) and _point(w.get('to'))]):
                errors.append(f'Cômodo {rid} tem perímetro sem parede entre {a} e {b}.')
    furniture_ids=set()
    for f in furniture:
        fid=f.get('id');rid=f.get('room_id')
        if not isinstance(fid,str) or not fid or fid in furniture_ids: errors.append('ID de mobiliário ausente/duplicado.');continue
        furniture_ids.add(fid)
        dims=f.get('size'); center=f.get('center'); degree=f.get('rotation_deg',0)
        if rid not in valid_polys or not _point(center) or not isinstance(dims,list) or len(dims)!=3 or any(not isinstance(x,(float,int)) or not .05<=x<=15 for x in dims) or not isinstance(degree,(float,int)):
            errors.append(f'Mobiliário {fid} com dados geométricos inválidos.');continue
        theta=math.radians(degree);co,si=math.cos(theta),math.sin(theta)
        corners=[]
        for x in [-dims[0]/2,dims[0]/2]:
            for y in [-dims[1]/2,dims[1]/2]: corners.append([center[0]+co*x-si*y,center[1]+si*x+co*y])
        if not all(_inside(p,valid_polys[rid]) for p in corners): errors.append(f'Mobiliário {fid} extrapola os limites do cômodo {rid}.')
        if f.get('color') and not HEX.fullmatch(f['color']): errors.append(f'Mobiliário {fid} com cor inválida.')
    evidence=project.get('evidence') or {}
    if evidence.get('scale_verified') and evidence.get('dimensions_confirmed_by_user'):
        fidelity='plant-validated-not-as-built'
    else:
        fidelity='conceptual-unverified'
        warnings.append('Escala ou dimensões não confirmadas: somente modelo conceitual, não representação fiel da planta.')
    if not evidence.get('building_as_built_verified'): warnings.append('Projeto não verificado in loco; a planta não comprova o imóvel executado.')
    if any(o.get('kind')=='arch' for w in walls for o in w.get('openings',[])) and not evidence.get('structural_approval'):
        warnings.append('Abertura em arco requer análise estrutural e autorização profissional antes de executar obra.')
    style=project.get('style') or {}
    if not HEX.fullmatch(style.get('wall_color','#DCDCDC')) or not HEX.fullmatch(style.get('default_floor_color','#C0B099')): errors.append('Paleta de cores inválida: usar #RRGGBB.')
    return {'ok':not errors, 'errors':errors,'warnings':warnings,'fidelity': fidelity if not errors else 'invalid',
            'stats':{'rooms':len(rooms),'walls':len(walls),'openings':sum(len(w.get('openings',[])) for w in walls),'furniture':len(furniture)}}


def _earclip(poly):
    pts=list(poly); indices=list(range(len(pts))); sign=1 if _area(pts)>0 else -1
    triangles=[]
    while len(indices)>3:
        found=False
        for i in range(len(indices)):
            a,b,c=(indices[i-1],indices[i],indices[(i+1)%len(indices)])
            if sign*_cross(pts[a],pts[b],pts[c])<=EPS: continue
            def in_tri(q):
                u=sign*_cross(pts[a],pts[b],q);v=sign*_cross(pts[b],pts[c],q);w=sign*_cross(pts[c],pts[a],q)
                return u>=-EPS and v>=-EPS and w>=-EPS
            if any(in_tri(pts[k]) for k in indices if k not in (a,b,c)): continue
            triangles.append((a,b,c)); indices.pop(i);found=True;break
        if not found: raise ValueError('Triangulação falhou: verifique o polígono.')
    triangles.append(tuple(indices));return triangles


def _slab(poly, thickness=.06):
    import trimesh
    n=len(poly);vertices=[(x,y,0) for x,y in poly]+[(x,y,-thickness) for x,y in poly]
    t=_earclip(poly); faces=[];sign=1 if _area(poly)>0 else -1
    for a,b,c in t:
        if sign>0: faces.extend([[a,b,c],[c+n,b+n,a+n]])
        else: faces.extend([[c,b,a],[a+n,b+n,c+n]])
    for i in range(n):
        j=(i+1)%n;faces.extend([[i,j,j+n],[i,j+n,i+n]])
    return trimesh.Trimesh(vertices=vertices,faces=faces,process=False)


def _wall_prism(a,b,thickness,lo,hi,bottom_a,top_a,bottom_b=None,top_b=None):
    import trimesh
    if bottom_b is None: bottom_b=bottom_a
    if top_b is None: top_b=top_a
    dx,dy=b[0]-a[0],b[1]-a[1];ln=math.hypot(dx,dy)
    ux,uy=dx/ln,dy/ln;nx,ny=-uy*thickness/2,ux*thickness/2
    start=(a[0]+ux*lo,a[1]+uy*lo);end=(a[0]+ux*hi,a[1]+uy*hi)
    v=[(start[0]+nx,start[1]+ny,bottom_a),(end[0]+nx,end[1]+ny,bottom_b),
       (end[0]+nx,end[1]+ny,top_b),(start[0]+nx,start[1]+ny,top_a),
       (start[0]-nx,start[1]-ny,bottom_a),(end[0]-nx,end[1]-ny,bottom_b),
       (end[0]-nx,end[1]-ny,top_b),(start[0]-nx,start[1]-ny,top_a)]
    faces=[[0,1,2],[0,2,3],[4,6,5],[4,7,6],[0,4,5],[0,5,1],[3,2,6],[3,6,7],[0,3,7],[0,7,4],[1,5,6],[1,6,2]]
    return trimesh.Trimesh(vertices=v,faces=faces,process=False)


def _rgba(color):
    c=color.lstrip('#');return [int(c[i:i+2],16) for i in (0,2,4)]+[255]


def _centroid(poly):
    x=sum(p[0] for p in poly)/len(poly);y=sum(p[1] for p in poly)/len(poly)
    if _inside((x,y),poly): return (x,y)
    # A triangle centroid will lie in a valid triangulated concave polygon.
    a,b,c=_earclip(poly)[0];return tuple(sum(poly[i][j] for i in (a,b,c))/3 for j in (0,1))


def plan_views(project):
    report=validate_project(project)
    if not report['ok']:raise ValueError('; '.join(report['errors']))
    result={}
    for room in project['rooms']:
        poly=room['polygon'];cx,cy=_centroid(poly)
        # 1/4 from center toward first vertex stays inside the center-to-vertex triangle in ordinary convex rooms.
        vx,vy=poly[0];cam=(.75*cx+.25*vx, .75*cy+.25*vy,1.6)
        result[room['id']]={'name':room.get('name',room['id']),'camera_m':[round(x,4) for x in cam],
                            'target_m':[round(cx,4),round(cy,4),1.3], 'status':'suggested-camera-check-furniture-occlusion'}
    return result


def build_scene(project, output_dir):
    report=validate_project(project)
    if not report['ok']: raise ValueError('Planta inválida: '+'; '.join(report['errors']))
    import trimesh
    from trimesh.transformations import rotation_matrix
    output=pathlib.Path(output_dir).resolve();output.mkdir(parents=True,exist_ok=True)
    scene=trimesh.Scene();style=project.get('style',{})
    scene.metadata={'schema_version': '1.0','fidelity':report['fidelity'],'provenance':project.get('evidence',{}),
                    'room_ids':[r['id'] for r in project['rooms']]}
    def add(geometry,label,color):
        geometry.visual.vertex_colors=_rgba(color)
        scene.add_geometry(geometry,node_name=label,geom_name=label)
    for room in project['rooms']:
        add(_slab(room['polygon']), 'floor:'+room['id'],room.get('floor_color',style.get('default_floor_color','#BBAA99')))
    pieces=0;archparts=0
    ceiling=project['level']['ceiling_height']
    for wall in project['walls']:
        a,b=wall['from'],wall['to'];th=wall['thickness'];wallheight=wall.get('height',ceiling)
        ln=math.dist(a,b);starts=0.;openinglist=sorted(wall.get('openings',[]),key=lambda o:o['offset'])
        def put(lo,hi,zlo,zhi,zlo2=None,zhi2=None,tag='solid'):
            nonlocal pieces
            if hi-lo<EPS or zhi-zlo<EPS: return
            geo=_wall_prism(a,b,th,lo,hi,zlo,zhi,zlo2,zhi2)
            add(geo,'wall:'+wall['id']+':'+tag+':'+str(pieces),style.get('wall_color','#EAE1D4'));pieces+=1
        for opening in openinglist:
            off=opening['offset'];end=off+opening['width'];kind=opening['kind']
            put(starts,off,0,wallheight,tag='pier')
            sill=opening.get('sill',0)
            put(off,end,0,sill,tag='under')
            if kind=='arch':
                # 24 continuous piecewise-linear facets trace an actual curved soffit in 3D.
                spring=opening['spring_height'];rise=opening['rise'];n=24
                def arc(x):return spring+rise*math.sqrt(max(0,1-(2*(x-off)/opening['width']-1)**2))
                for i in range(n):
                    left=off+(end-off)*i/n;right=off+(end-off)*(i+1)/n
                    lo,hi=arc(left),arc(right)
                    if min(lo,hi)<wallheight-EPS:
                        put(left,right,lo,wallheight,lo,wallheight,tag='arch-head')
                        # Replace horizontal underside with sloped edge while retaining vertical top.
                        # For curved soffit the previous put uses left bottom at both sides; updated below.
                        # Existing mesh is updated by accurate face vertex coordinates.
                        label='wall:'+wall['id']+':arch-head:'+str(pieces-1)
                        mesh=scene.geometry[label];verts=mesh.vertices.copy();verts[[1,5],2]=hi
                        mesh.vertices=verts
                        archparts+=1
            else:
                put(off,end,sill+opening['height'],wallheight,tag='lintel')
            starts=end
        put(starts,ln,0,wallheight,tag='pier')
    for f in project.get('furniture',[]):
        sx,sy,sz=f['size'];cx,cy=f['center']
        mesh=trimesh.creation.box(extents=[sx,sy,sz]);mesh.apply_translation([0,0,sz/2])
        mesh.apply_transform(rotation_matrix(math.radians(f.get('rotation_deg',0)),[0,0,1],point=[0,0,0]))
        mesh.apply_translation([cx,cy,0])
        add(mesh,'furniture:'+f['id'],f.get('color','#846753'))
    target=output/'edificacao_modelo.glb'
    target.write_bytes(scene.export(file_type='glb'))
    views=output/'vistas_comodos.json';views.write_text(json.dumps(plan_views(project),ensure_ascii=False,indent=2),encoding='utf-8')
    audit=output/'auditoria_geometrica.json'
    audit_data={**report,'openings':[o['id'] for w in project['walls'] for o in w.get('openings',[])],
                'geometry':{'wall_parts':pieces,'arch_header_segments':archparts,'floor_parts':len(project['rooms'])},
                'model_format':'GLB/glTF 2.0','visual_fidelity':'geometric; furnishings are volume placeholders, not photoreal assets'}
    audit.write_text(json.dumps(audit_data,ensure_ascii=False,indent=2),encoding='utf-8')
    return {'ok':True,'model_glb':str(target),'views_json':str(views),'audit_json':str(audit),
            'fidelity':report['fidelity'],'warnings':report['warnings'],'openings':audit_data['openings'],
            'geometry':audit_data['geometry']}


def inspect_source(path):
    p=pathlib.Path(path).expanduser().resolve()
    if not p.is_file(): raise ValueError('Arquivo não encontrado.')
    if p.stat().st_size>MAX_INPUT_BYTES: raise ValueError('Arquivo excede 40 MB; divida ou reduza antes da análise.')
    suffix=p.suffix.lower()
    base={'filename':p.name,'size_bytes':p.stat().st_size,'geometry_reconstructed':False,
          'warning':'Leitura de metadados/primitivas não autentica medidas ou converte automaticamente em BIM.'}
    if suffix in ('.png','.jpg','.jpeg','.webp','.tif','.tiff'):
        from PIL import Image
        with Image.open(p) as im:
            return {**base,'format':'raster-image','width_px':im.width,'height_px':im.height,'mode':im.mode,
                    'scale_status':'manual-calibration-required'}
    if suffix=='.pdf':
        import fitz
        d=fitz.open(p)
        pages=[]
        for i in range(min(3,len(d))):
            pg=d.load_page(i);draws=pg.get_drawings();samples=[]
            for drawing in draws[:100]:
                for obj in drawing.get('items',[])[:10]:
                    if obj[0]=='l':samples.append([[round(obj[1].x,2),round(obj[1].y,2)],[round(obj[2].x,2),round(obj[2].y,2)]])
                    if len(samples)>=60:break
                if len(samples)>=60:break
            pages.append({'page':i+1,'width_pt':round(pg.rect.width,2),'height_pt':round(pg.rect.height,2),
                          'vector_drawing_count':len(draws),'sample_lines_points':samples,
                          'text_excerpt_untrusted':pg.get_text('text')[:800]})
        return {**base,'format':'pdf','total_pages':len(d),'pages_sampled':pages,'units':'points-in-pdf-not-meters'}
    if suffix=='.dxf':
        import ezdxf
        d=ezdxf.readfile(p);ents=list(d.modelspace());segments=[]
        for e in ents:
            if e.dxftype()=='LINE' and len(segments)<100:
                a,b=e.dxf.start,e.dxf.end
                segments.append({'layer':e.dxf.layer,'a':[a.x,a.y],'b':[b.x,b.y]})
        return {**base,'format':'dxf','dxf_version':d.dxfversion,'insunits':d.header.get('$INSUNITS',0),
                'layers':[layer.dxf.name for layer in d.layers][:80], 'entities':len(ents),'line_samples':segments,
                'units_warning':'A variável INSUNITS é informativa; confirme escala e layers antes de reconstruir.'}
    if suffix=='.ifc':
        try:import ifcopenshell
        except ImportError:
            return {**base,'format':'ifc','parsing_status':'needs-ifcopenshell',
                    'instructions':'Instale ifcopenshell; IFC não é convertido em GLB automaticamente nesta versão.'}
        d=ifcopenshell.open(str(p))
        return {**base,'format':'ifc','parsing_status':'inspected-only',
                'counts':{key:len(d.by_type(key)) for key in ('IfcWall','IfcSpace','IfcDoor','IfcWindow','IfcSlab')},
                'warning':'Elementos detectados, mas geometria IFC completa ainda não convertida automaticamente.'}
    raise ValueError('Formato não aceito. Use PDF, PNG/JPEG/WEBP/TIFF, DXF, IFC ou JSON normalizado.')


def render_views(model_glb, views_json, output_dir, blender_executable='blender', samples=128):
    """Render approved GLB with Blender Cycles, preserving the model source.

    Requires Blender installed on the execution host; never silently downgrades
    quality to a generic CPU preview or substitutes AI-generated geometry.
    """
    if pathlib.Path(blender_executable).name.lower() not in ('blender', 'blender.exe'):
        raise ValueError('Somente o executável Blender é permitido para renderização.')
    binary = shutil.which(blender_executable) if blender_executable == 'blender' else blender_executable
    if not binary or not pathlib.Path(binary).is_file():
        raise RuntimeError('Blender Cycles não instalado neste executor; render físico indisponível.')
    if type(samples) is not int or not 16 <= samples <= 1024:
        raise ValueError('samples deve ficar entre 16 e 1024.')
    model = pathlib.Path(model_glb).resolve()
    views = pathlib.Path(views_json).resolve()
    if not model.is_file() or model.suffix.lower() != '.glb' or not views.is_file():
        raise ValueError('Arquivos de modelo e de vistas inválidos.')
    definitions = json.loads(views.read_text(encoding='utf-8'))
    if not isinstance(definitions, dict) or not 1 <= len(definitions) <= 150:
        raise ValueError('Lista de vistas inválida ou vazia.')
    dest = pathlib.Path(output_dir).resolve()
    dest.mkdir(parents=True, exist_ok=True)
    script = pathlib.Path(__file__).with_name('blender_render.py')
    args = [str(binary), '--background', '--python', str(script), '--', str(model),
            str(views), str(dest), str(samples)]
    # Renderings can be expensive. Keep an upper bound and always report failure.
    run = subprocess.run(args, capture_output=True, text=True, timeout=1800, check=False)
    if run.returncode:
        raise RuntimeError('Blender Cycles falhou: ' + run.stderr[-1800:])
    images = sorted(dest.glob('comodo_*.png'))
    if len(images) != len(definitions):
        raise RuntimeError(f'Blender gerou {len(images)} de {len(definitions)} vistas solicitadas.')
    if any(p.stat().st_size < 100 or p.open('rb').read(8) != b'\x89PNG\r\n\x1a\n' for p in images):
        raise RuntimeError('Uma ou mais imagens Blender possuem PNG inválido.')
    manifest = dest / 'render_manifest.json'
    if not manifest.is_file():
        raise RuntimeError('Renderizador não produziu manifesto auditável.')
    return {'ok': True, 'pngs': [str(p) for p in images],
            'renderer': 'Blender Cycles (path tracing + denoising)',
            'manifest': str(manifest),
            'warning': 'Render físico da geometria aprovada: materiais e aparência real exigem evidência; não prova as-built.'}
