"""Dependency-light MCP stdio server; JSON-RPC 2.0 one JSON message per line.
Runs on the user's own computer (for local hosts), not in ChatGPT Web.
"""
import json
import pathlib
import sys
from core import validate_project, build_scene, inspect_source, plan_views, render_views
from assisted_import import extract_trace, calibrate_trace, suggest_rooms, reviewed_project
from room_preview import render_previews
from render_pipeline import build_and_render_physical
from review_editor import create_review_editor

SCHEMA = {'type':'object','additionalProperties':False}

TOOLS = [
 {'name':'inspect_source','description':'Inspeciona PDF/DXF/IFC/imagem de planta: metadados, layers ou amostras de geometria. Não inventa cômodos ou medidas.',
  'inputSchema':{**SCHEMA,'properties':{'path':{'type':'string','description':'Caminho absoluto do arquivo autorizado pelo usuário'}},'required':['path']}},
 {'name':'validate_project','description':'Audita um projeto JSON normalizado com paredes, aberturas, cômodos, mobiliário e proveniência.',
  'inputSchema':{**SCHEMA,'properties':{'project':{'type':'object'}},'required':['project']}},
 {'name':'plan_views','description':'Planeja câmera 3D para cada cômodo sem alterar a geometria.',
  'inputSchema':{**SCHEMA,'properties':{'project':{'type':'object'}},'required':['project']}},
 {'name':'build_scene','description':'Constrói geometria real em escala do JSON normalizado e exporta GLB, vistas e auditoria. Precisa de trimesh.',
  'inputSchema':{**SCHEMA,'properties':{'project':{'type':'object'},'output_dir':{'type':'string'}},'required':['project','output_dir']}},
 {'name':'extract_trace','description':'Lê segmentos candidatos de planta PDF vetorial, DXF ou PNG/JPG via Hough; nunca inventa paredes, medidas ou cômodos.',
  'inputSchema':{**SCHEMA,'properties':{'path':{'type':'string'},'page':{'type':'integer'},'layers':{'type':'array','items':{'type':'string'}},'max_lines':{'type':'integer'}},'required':['path']}},
 {'name':'calibrate_trace','description':'Calibra o traçado por dois pontos de referência e distância confirmada em metros; não aprova cômodos automaticamente.',
  'inputSchema':{**SCHEMA,'properties':{'trace':{'type':'object'},'reference_a':{'type':'array'},'reference_b':{'type':'array'},'length_m':{'type':'number'}},'required':['trace','reference_a','reference_b','length_m']}},
 {'name':'suggest_rooms','description':'Propõe regiões poligonais a partir do traçado escalado; regiões são candidatas, não cômodos validados.',
  'inputSchema':{**SCHEMA,'properties':{'scaled':{'type':'object'},'max_rooms':{'type':'integer'},'snap_tolerance_m':{'type':'number'}},'required':['scaled']}},
 {'name':'reviewed_project','description':'Normaliza paredes e polígonos explicitamente aprovados após calibração; verifica consistência do modelo.',
  'inputSchema':{**SCHEMA,'properties':{'scaled':{'type':'object'},'rooms':{'type':'array'},'wall_ids':{'type':'array','items':{'type':'string'}},
    'wall_thickness_m':{'type':'number'},'ceiling_height_m':{'type':'number'},'approval':{'type':'boolean'},
    'openings':{'type':'array'},'furniture':{'type':'array'},'style':{'type':'object'},'project_name':{'type':'string'},'derive_walls_from_rooms':{'type':'boolean'}},
    'required':['scaled','rooms','wall_ids','approval']}},
 {'name':'create_review_editor','description':'Gera editor HTML offline para calibrar por cliques, selecionar paredes e desenhar cômodos sobre os segmentos extraídos.',
  'inputSchema':{**SCHEMA,'properties':{'trace':{'type':'object'},'output_html':{'type':'string'}},'required':['trace','output_html']}},
 {'name':'render_previews','description':'Renderiza PNGs geométricos via CPU sem Blender. Não são fotografias fotorrealistas.',
  'inputSchema':{**SCHEMA,'properties':{'model_glb':{'type':'string'},'views_json':{'type':'string'},'output_dir':{'type':'string'},
    'width':{'type':'integer'},'height':{'type':'integer'}},'required':['model_glb','views_json','output_dir']}},
 {'name':'build_and_preview','description':'Cria GLB e gera prévias PNG de todos os cômodos com rastreabilidade em uma operação.',
  'inputSchema':{**SCHEMA,'properties':{'project':{'type':'object'},'output_dir':{'type':'string'}},'required':['project','output_dir']}},
 {'name':'build_and_render_physical','description':'Valida planta confirmada, gera GLB métrico e renderiza cada cômodo com Blender Cycles instalado localmente, retornando PNGs e auditoria; não comprova as-built nem réplica fotográfica.',
  'inputSchema':{**SCHEMA,'properties':{'project':{'type':'object'},'output_dir':{'type':'string'},'blender_executable':{'type':'string','default':'blender'},'samples':{'type':'integer','minimum':16,'maximum':1024}},
   'required':['project','output_dir']}},
 {'name':'render_views','description':'Renderiza PNGs cômodo a cômodo usando Blender instalado localmente. Não promete fotorrealismo.',
  'inputSchema':{**SCHEMA,'properties':{'model_glb':{'type':'string'},'views_json':{'type':'string'},'output_dir':{'type':'string'},
               'blender_executable':{'type':'string','default':'blender'},'samples':{'type':'integer','minimum':1,'maximum':256}},
               'required':['model_glb','views_json','output_dir']}},
]
BY_NAME={t['name']:t for t in TOOLS}


def dispatch(message):
    if not isinstance(message,dict) or message.get('jsonrpc')!='2.0':
        return {'jsonrpc':'2.0','id':message.get('id') if isinstance(message,dict) else None,
                'error':{'code':-32600,'message':'Invalid Request'}}
    if 'id' not in message:return None  # notifications, incl. initialized and cancelled
    mid=message['id'];method=message.get('method');params=message.get('params') or {}
    try:
        if method=='initialize':
            version=params.get('protocolVersion','2025-11-25')
            result={'protocolVersion':version,'capabilities':{'tools':{}},
                    'serverInfo':{'name':'arq-fiel-3d','version':'0.2.0'},
                    'instructions':'Leitura preliminar de plantas + GLB em escala a partir de dados confirmados. Sem certificação as-built/estrutural.'}
        elif method=='ping': result={}
        elif method=='tools/list':result={'tools':TOOLS}
        elif method=='tools/call':
            name=params.get('name');args=params.get('arguments') or {}
            if name not in BY_NAME:raise ValueError('Ferramenta desconhecida: '+str(name))
            if not isinstance(args,dict):raise ValueError('arguments precisa ser objeto.')
            required=BY_NAME[name]['inputSchema']['required']
            if any(k not in args for k in required):raise ValueError('Faltam argumentos obrigatórios: '+', '.join(k for k in required if k not in args))
            if name=='inspect_source': data=inspect_source(args['path'])
            elif name=='validate_project':data=validate_project(args['project'])
            elif name=='plan_views':data=plan_views(args['project'])
            elif name=='build_scene':data=build_scene(args['project'],args['output_dir'])
            elif name=='extract_trace':data=extract_trace(args['path'],args.get('page',0),args.get('layers'),args.get('max_lines',1600))
            elif name=='calibrate_trace':data=calibrate_trace(args['trace'],args['reference_a'],args['reference_b'],args['length_m'])
            elif name=='suggest_rooms':data=suggest_rooms(args['scaled'],args.get('max_rooms',75),args.get('snap_tolerance_m',.025))
            elif name=='reviewed_project':data=reviewed_project(args['scaled'],args['rooms'],args['wall_ids'],
                args.get('wall_thickness_m',.15),args.get('ceiling_height_m',2.7),args['approval'],
                args.get('openings'),args.get('furniture'),args.get('style'),args.get('project_name','Planta assistida'),args.get('derive_walls_from_rooms',False))
            elif name=='create_review_editor':data=create_review_editor(args['trace'],args['output_html'])
            elif name=='render_previews':data=render_previews(args['model_glb'],args['views_json'],args['output_dir'],args.get('width',960),args.get('height',720))
            elif name=='build_and_preview':
                model=build_scene(args['project'],args['output_dir'])
                preview=render_previews(model['model_glb'],model['views_json'],str(pathlib.Path(args['output_dir'])/'previas'))
                data={**model,'previews':preview}
            elif name=='build_and_render_physical':data=build_and_render_physical(args['project'],args['output_dir'],args.get('samples',128),args.get('blender_executable','blender'))
            else:data=render_views(args['model_glb'],args['views_json'],args['output_dir'],args.get('blender_executable','blender'),args.get('samples',32))
            result={'content':[{'type':'text','text':json.dumps(data,ensure_ascii=False)}],'structuredContent':data,'isError':False}
        else:
            return {'jsonrpc':'2.0','id':mid,'error':{'code':-32601,'message':'Method not found'}}
        return {'jsonrpc':'2.0','id':mid,'result':result}
    except Exception as exc:
        if method=='tools/call':
            error={'error':str(exc),'tool':params.get('name')}
            return {'jsonrpc':'2.0','id':mid,'result':{'isError':True,'content':[{'type':'text','text':json.dumps(error,ensure_ascii=False)}],
                'structuredContent':error}}
        return {'jsonrpc':'2.0','id':mid,'error':{'code':-32602,'message':str(exc)}}


def main():
    for line in sys.stdin:
        if not line.strip():continue
        try:
            item=json.loads(line)
            response=dispatch(item)
            if response is not None:
                sys.stdout.write(json.dumps(response,ensure_ascii=False,separators=(',',':'))+'\n')
                sys.stdout.flush()
        except Exception as exc:
            print('MCP request error: '+str(exc),file=sys.stderr)


if __name__=='__main__':main()
