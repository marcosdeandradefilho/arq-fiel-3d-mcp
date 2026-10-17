"""Auditable, human-in-the-loop extraction of 2D linework from floorplans.

No source primitive is assumed to be a wall. A user must provide a scale
reference, select geometry, and approve rooms before a GLB may be called
'plant validated'. Source text never becomes executable instruction.
"""
import hashlib
import math
import pathlib
from core import MAX_INPUT_BYTES, _point, _simple_polygon

MAX_LINES=1600


def _safe_path(path):
    p=pathlib.Path(path).expanduser().resolve()
    if not p.is_file() or p.suffix.lower() not in ('.pdf','.dxf','.png','.jpg','.jpeg','.webp','.tif','.tiff'):
        raise ValueError('Fonte inexistente ou formato de planta não suportado.')
    if p.stat().st_size>MAX_INPUT_BYTES:raise ValueError('Planta excede o limite de 40 MB.')
    return p


def _line(a,b,layer,source,tag=None):
    x=[float(a[0]),float(a[1])];y=[float(b[0]),float(b[1])]
    if not all(math.isfinite(v) for v in (*x,*y)) or math.dist(x,y)<.01:return None
    return {'a':x,'b':y,'layer':str(layer)[:100], 'origin':str(source)[:60], 'source_id':str(tag)[:60] if tag is not None else None}


def extract_trace(path,page=0,layers=None,max_lines=MAX_LINES):
    """Read original coordinates. For raster lines are Hough candidates only."""
    p=_safe_path(path)
    if type(page)!=int or page<0:raise ValueError('Número de página inválido.')
    if type(max_lines)!=int or not 10<=max_lines<=MAX_LINES:raise ValueError('max_lines deve ficar entre 10 e 1600.')
    if layers is not None and (not isinstance(layers,list) or len(layers)>200 or not all(isinstance(x,str) for x in layers)):
        raise ValueError('Filtro de layers inválido.')
    allow=set(layers) if layers is not None else None
    suf=p.suffix.lower();result=[];source_units='drawing-units';warnings=[]
    def put(a,b,layer,origin,tag):
        if len(result)>=max_lines:return
        if allow is not None and str(layer) not in allow:return
        line=_line(a,b,layer,origin,tag)
        if line:result.append({'id':'L'+str(len(result)+1),**line})
    if suf=='.dxf':
        import ezdxf
        doc=ezdxf.readfile(p)
        ents=doc.modelspace()
        for ix,e in enumerate(ents):
            if ix>100000: warnings.append('Limite de 100.000 entidades atingido.');break
            kind=e.dxftype();layer=e.dxf.layer
            if kind=='LINE':put(list(e.dxf.start)[:2],list(e.dxf.end)[:2],layer,kind,ix)
            elif kind=='LWPOLYLINE':
                # Straight segments only. Bulge arcs require explicit manual review.
                pairs=list(e.get_points('xyb'))
                for j in range(len(pairs)-(0 if e.closed else 1)):
                    a,b=pairs[j],pairs[(j+1)%len(pairs)]
                    if abs(a[2])>1e-7: warnings.append('DXF: arco bulge ignorado; revisar manualmente.');continue
                    put(a[:2],b[:2],layer,kind,f'{ix}:{j}')
            if len(result)>=max_lines:break
        source_units='drawing-units (DXF INSUNITS=' + str(doc.header.get('$INSUNITS',0)) + ')'
        fmt='dxf';status='source-primitives-not-verified-walls'
    elif suf=='.pdf':
        import fitz
        with fitz.open(p) as doc:
            if page>=len(doc):raise ValueError('Página fora do PDF.')
            pg=doc[page];draws=pg.get_drawings()
            for j,d in enumerate(draws[:10000]):
                for k,item in enumerate(d['items']):
                    if item[0]=='l':put((item[1].x,item[1].y),(item[2].x,item[2].y),'PDF', 'vector-line',f'{j}:{k}')
                    elif item[0]=='re':
                        r=item[1];points=[(r.x0,r.y0),(r.x1,r.y0),(r.x1,r.y1),(r.x0,r.y1)]
                        for i in range(4):put(points[i],points[(i+1)%4],'PDF','vector-rectangle',f'{j}:{k}:{i}')
                    if len(result)>=max_lines:break
                if len(result)>=max_lines:break
            if not result: warnings.append('PDF sem vetores lineares úteis; renderize a página e use a extração raster.')
        fmt='pdf';source_units='PDF points';status='source-primitives-not-verified-walls'
    else:
        import cv2
        im=cv2.imread(str(p),cv2.IMREAD_GRAYSCALE)
        if im is None:raise ValueError('Imagem ilegível.')
        h,w=im.shape;scale=min(1.,2400/max(w,h))
        work=cv2.resize(im,None,fx=scale,fy=scale,interpolation=cv2.INTER_AREA) if scale<1 else im
        edges=cv2.Canny(work,55,160)
        lines=cv2.HoughLinesP(edges,1,math.pi/180,threshold=60,minLineLength=max(25,int(min(work.shape)*.07)),maxLineGap=10)
        for i,item in enumerate(lines if lines is not None else []):
            x1,y1,x2,y2=[float(v)/scale for v in item[0]]
            put([x1,y1],[x2,y2],'RASTER','Hough-candidate',i)
        warnings.append('Linhas raster são detecções aproximadas com possíveis duplicatas, mobiliário e anotações; confirmar cada parede.')
        fmt='raster-image';source_units='pixels';status='raster-line-candidates-unverified'
    if len(result)>=max_lines:warnings.append('Linhas truncadas no limite solicitado; filtrar página/layers para mais precisão.')
    return {'format':fmt,'source_file':p.name,'source_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
            'source_units':source_units,'page':page if fmt=='pdf' else None,'lines':result,
            'warnings':warnings,'source_geometry':status,'dimensions_verified':False,
            'walls_verified':False,'rooms_verified':False}


def calibrate_trace(trace,reference_a,reference_b,length_m):
    if not isinstance(trace,dict) or not isinstance(trace.get('lines'),list):raise ValueError('Traçado inválido.')
    if not _point(reference_a) or not _point(reference_b) or math.dist(reference_a,reference_b)<1e-6:
        raise ValueError('Coordenadas da referência de medida inválidas.')
    if type(length_m) not in (int,float) or not math.isfinite(length_m) or not .05<=length_m<=100:
        raise ValueError('Insira referência real entre 0,05 e 100 metros.')
    factor=length_m/math.dist(reference_a,reference_b)
    if not 1e-9<factor<10000:raise ValueError('Escala fora dos limites.')
    origin=list(reference_a)
    def convert(p):return [round((p[k]-origin[k])*factor,5) for k in range(2)]
    lines=[];ids=set()
    for line in trace['lines']:
        if not _point(line.get('a')) or not _point(line.get('b')):raise ValueError('Segmento inválido na fonte.')
        lid=line.get('id')
        if not isinstance(lid,str) or not lid or lid in ids:raise ValueError('IDs de segmento inválidos ou duplicados.')
        ids.add(lid)
        lines.append({**line,'a_m':convert(line['a']),'b_m':convert(line['b'])})
    return {**trace,'status':'scaled-candidate-not-reviewed',
            'meters_per_source_unit':factor,'source_origin':origin,'lines_m':lines,
            'scale_reference':{'a':list(reference_a),'b':list(reference_b),'length_m':length_m},
            'evidence':{'scale_verified':True,'dimensions_confirmed_by_user':False,'building_as_built_verified':False}}


def suggest_rooms(scaled,max_rooms=75,snap_tolerance_m=.025,min_area_m2=.5):
    """Polygonizes candidate segments; DOES NOT assign wall semantics or certify rooms."""
    from shapely.geometry import LineString
    from shapely.ops import unary_union,polygonize
    if 'lines_m' not in scaled:raise ValueError('Calibre a escala antes de sugerir cômodos.')
    if type(max_rooms)!=int or not 1<=max_rooms<=150:raise ValueError('max_rooms inválido.')
    if not .001<=snap_tolerance_m<=.3:raise ValueError('Tolerância fora do intervalo.')
    def snap(p):return tuple(round(float(x)/snap_tolerance_m)*snap_tolerance_m for x in p)
    edges=[]
    for l in scaled['lines_m']:
        a,b=snap(l['a_m']),snap(l['b_m'])
        if math.dist(a,b)>snap_tolerance_m:edges.append(LineString([a,b]))
    polygons=list(polygonize(unary_union(edges))) if edges else []
    polygons=sorted((p for p in polygons if p.area>=min_area_m2),key=lambda x:-x.area)[:max_rooms]
    return {'status':'candidate-room-boundaries-not-approved','candidates':[
        {'id':'candidate-'+str(i+1),'polygon_m':[[round(x,4),round(y,4)] for x,y in list(poly.exterior.coords)[:-1]],
         'area_m2':round(poly.area,4),'confirmed':False} for i,poly in enumerate(polygons)],
        'warning':'Regiões formadas por segmentos não provam a existência de ambientes; aprovar manualmente e excluir cotas/mobiliário.'}


def reviewed_project(scaled,rooms,wall_ids,wall_thickness_m=.15,ceiling_height_m=2.7,approval=False,
                     openings=None,furniture=None,style=None,project_name='Planta assistida',derive_walls_from_rooms=False):
    """Converts user-approved line selections and room vertices into normalized geometry.

    Room polygon_source is in original source coordinates (not meters).
    Opening offsets/widths/heights are explicitly in meters, measured from wall a_m.
    """
    if approval is not True:raise ValueError('Exige aprovação explícita de escala, paredes e polígonos pelo usuário.')
    if 'lines_m' not in scaled or 'source_origin' not in scaled:raise ValueError('Escala não calibrada.')
    if not isinstance(rooms,list) or not isinstance(wall_ids,list) or len(rooms)>150 or len(wall_ids)>1500:raise ValueError('Seleções inválidas.')
    if not isinstance(wall_thickness_m,(int,float)) or not .05<=wall_thickness_m<=1.5:raise ValueError('Espessura inválida.')
    if not isinstance(ceiling_height_m,(int,float)) or not 2<=ceiling_height_m<=15:raise ValueError('Pé-direito inválido.')
    ids=set(wall_ids);by_id={line['id']:line for line in scaled['lines_m']}
    if not ids<=set(by_id):raise ValueError('Parede desconhecida selecionada.')
    if len(ids)!=len(wall_ids):raise ValueError('Parede selecionada mais de uma vez.')
    origin=scaled['source_origin'];factor=scaled['meters_per_source_unit']
    def convert(p):
        if not _point(p):raise ValueError('Vértice de cômodo inválido.')
        return [round((p[k]-origin[k])*factor,5) for k in range(2)]
    r=[]
    for room in rooms:
        points=room.get('polygon_source')
        if not isinstance(points,list) or not all(_point(p) for p in points):raise ValueError('Polígono fonte inválido.')
        poly=[convert(p) for p in points]
        if not _simple_polygon(poly):raise ValueError('Polígono confirmado autointersectado ou degenerado.')
        r.append({'id':room['id'],'name':room.get('name',room['id']),'polygon':poly,
                  **({'floor_color':room['floor_color']} if 'floor_color' in room else {})})
    if derive_walls_from_rooms:
        # Only edges of manually drawn AND explicitly approved room polygons.
        # Shared edges are included once, regardless of orientation.
        segments={}
        for room in r:
            poly=room['polygon']
            for a,b in zip(poly,poly[1:]+poly[:1]):
                p1,p2=tuple(a),tuple(b)
                key=tuple(sorted((p1,p2)))
                segments[key]=key
        walls=[{'id':f'outline-{i:03d}','from':list(a),'to':list(b),
                'thickness':wall_thickness_m,'openings':[]}
                for i,(a,b) in enumerate(sorted(segments),1)]
    else:
        walls=[{'id':wid,'from':by_id[wid]['a_m'],'to':by_id[wid]['b_m'],'thickness':wall_thickness_m,
            'openings':[{'id':o['id'],'kind':o['kind'],'offset':o['offset'],'width':o['width'],
                 **{k:o[k] for k in ('height','sill','spring_height','rise') if k in o}}
                 for o in (openings or []) if o.get('wall_id')==wid]}
           for wid in wall_ids]
    used_opening_wall_ids={o.get('wall_id') for o in (openings or [])}
    all_wall_ids={w['id'] for w in walls}
    if not used_opening_wall_ids <= all_wall_ids:raise ValueError('Abertura referencia parede desconhecida.')
    if derive_walls_from_rooms:
        for w in walls:
            w['openings']=[{'id':o['id'],'kind':o['kind'],'offset':o['offset'],'width':o['width'],
                **{k:o[k] for k in ('height','sill','spring_height','rise') if k in o}}
                for o in (openings or []) if o.get('wall_id')==w['id']]
    proj={'schema_version':'1.0','project':{'name':project_name,'units':'m','source_note':'Traçado calibrado e aprovado manualmente; NÃO é as-built'},
          'evidence':{'source_file':scaled.get('source_file'),'source_sha256':scaled.get('source_sha256'),
                      'source_type':scaled.get('format'),'scale_verified':True,'dimensions_confirmed_by_user':True,
                      'building_as_built_verified':False,'structural_approval':False,'approval_type':'manual-source-tracing',
                      'scale_reference':scaled.get('scale_reference'),
                      'wall_method':'user-approved-room-boundaries' if derive_walls_from_rooms else 'approved-extracted-segments'},
          'level':{'id':'pavimento-1','ceiling_height':ceiling_height_m},
          'rooms':r,'walls':walls,'furniture':furniture or [],'style':style or {},'constraints':[]}
    from core import validate_project
    check=validate_project(proj)
    if not check['ok']:raise ValueError('Geometria revisada inconsistente: '+'; '.join(check['errors']))
    return proj
