"""Stateless authenticated MCP over HTTP for Vercel Python Functions.
Geometry only; Blender/Cycles remains available via local MCP runtime.
Project inputs are processed in ephemeral temporary directories, not stored.
"""
import base64
import hmac
import json
import os
import pathlib
import re
import sys
import tempfile
from fastapi import FastAPI,Request
from fastapi.responses import JSONResponse,Response

sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'runtime'))
from server import dispatch,TOOLS
from assisted_import import extract_trace
from core import build_scene
from room_preview import render_previews

app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None)
ALLOWED={'validate_project','plan_views','calibrate_trace','suggest_rooms','reviewed_project'}
ALLOWED_TOOLS=[tool for tool in TOOLS if tool['name'] in ALLOWED]
ALLOWED_TOOLS.extend([
 {'name':'extract_trace_source','description':'Extrai segmentos de PDF/DXF/imagem enviados como bytes base64 (máx. 1,5MB), sem armazenar. Linhas não são paredes confirmadas.',
  'inputSchema':{'type':'object','properties':{'source_base64':{'type':'string'},'extension':{'type':'string'},'page':{'type':'integer'}},
    'required':['source_base64','extension'],'additionalProperties':False}},
 {'name':'export_glb','description':'Exporta GLB em escala como base64 a partir de projeto JSON validado; não é foto ou levantamento estrutural.',
  'inputSchema':{'type':'object','properties':{'project':{'type':'object'}},'required':['project'],'additionalProperties':False}},
 {'name':'preview_room','description':'Retorna PNG geométrico de um cômodo via MCP image; não é fotorrealista. Motor Blender disponível apenas no MCP local.',
  'inputSchema':{'type':'object','properties':{'project':{'type':'object'},'room_id':{'type':'string'}},'required':['project'],'additionalProperties':False}}
])


def _response(mid,data):return {'jsonrpc':'2.0','id':mid,'result':data}

def _tools_result(data,extra_content=None):
    entries=[{'type':'text','text':json.dumps(data,ensure_ascii=False)}]
    if extra_content:entries.extend(extra_content)
    return {'content':entries,'structuredContent':data,'isError':False}

def _fail(exc):
    item={'error':str(exc)[:500]}
    return {'content':[{'type':'text','text':json.dumps(item,ensure_ascii=False)}],'structuredContent':item,'isError':True}

@app.get('/api/health')
def health():return {'status':'running','name':'arq-fiel-3d-mcp','version':'0.3.1',
                      'mcp_auth_configured':bool(os.getenv('ARQFIEL_MCP_API_KEY')),
                      'renderer':'CPU geometric preview; Blender Cycles requires separately provisioned compute'}

@app.post('/api/mcp')
async def mcp(request:Request):
    secret=os.getenv('ARQFIEL_MCP_API_KEY','')
    if not secret:return JSONResponse({'error':'MCP token not configured'},status_code=503)
    auth=request.headers.get('authorization','')
    if not auth.startswith('Bearer ') or not hmac.compare_digest(auth[7:],secret):
        return JSONResponse({'error':'Authentication required'},status_code=401)
    origin=request.headers.get('origin','')
    if origin and origin not in ('https://chatgpt.com','https://chat.openai.com'):
        return JSONResponse({'error':'Untrusted Origin'},status_code=403)
    data_bytes=await request.body()
    if len(data_bytes)>3_500_000:return JSONResponse({'error':'MCP request exceeds 3.5MB'},status_code=413)
    try:msg=json.loads(data_bytes)
    except Exception:return JSONResponse({'jsonrpc':'2.0','id':None,'error':{'code':-32700,'message':'Invalid JSON'}})
    if not isinstance(msg,dict):return JSONResponse({'jsonrpc':'2.0','id':None,'error':{'code':-32600,'message':'Request must be object'}})
    if msg.get('jsonrpc')!='2.0':return JSONResponse({'jsonrpc':'2.0','id':msg.get('id'),'error':{'code':-32600,'message':'JSONRPC 2.0 required'}})
    if 'id' not in msg:return Response(status_code=202)
    mid=msg['id'];method=msg.get('method');args=(msg.get('params') or {}).get('arguments') or {}
    if method=='initialize':
        reply=dispatch(msg)
        reply['result']['serverInfo']['version']='0.3.1'
        return JSONResponse(reply)
    if method=='ping':return JSONResponse(_response(mid,{}))
    if method=='tools/list':return JSONResponse(_response(mid,{'tools':ALLOWED_TOOLS}))
    if method!='tools/call':return JSONResponse({'jsonrpc':'2.0','id':mid,'error':{'code':-32601,'message':'Method not found'}})
    name=(msg.get('params') or {}).get('name')
    if name not in {t['name'] for t in ALLOWED_TOOLS}:return JSONResponse(_response(mid,_fail(ValueError('Ferramenta não disponível na execução remota.'))))
    if not isinstance(args,dict):return JSONResponse(_response(mid,_fail(ValueError('Argumentos inválidos.'))))
    try:
        if name in ALLOWED:
            result=dispatch(msg)
            return JSONResponse(result)
        if name=='extract_trace_source':
            extension=args.get('extension')
            if extension not in ('.pdf','.dxf','.png','.jpg','.jpeg','.webp','.tif','.tiff'):raise ValueError('Formato não permitido.')
            encoded=args.get('source_base64')
            if not isinstance(encoded,str) or len(encoded)>2_200_000:raise ValueError('Arquivo excede 1,5MB.')
            raw=base64.b64decode(encoded,validate=True)
            if len(raw)>1_500_000:raise ValueError('Arquivo excede 1,5MB.')
            with tempfile.TemporaryDirectory(prefix='arqfiel-source-') as dirname:
                p=pathlib.Path(dirname)/('input'+extension)
                p.write_bytes(raw)
                result=extract_trace(str(p),page=args.get('page',0),max_lines=300)
            return JSONResponse(_response(mid,_tools_result(result)))
        project=args['project']
        if not isinstance(project,dict) or len(project.get('rooms',[]))>20 or len(project.get('walls',[]))>200:
            raise ValueError('Projeto grande demais para processamento serverless; use o MCP local.')
        with tempfile.TemporaryDirectory(prefix='arqfiel-3d-') as dirname:
            out=build_scene(project,dirname)
            if name=='export_glb':
                raw=pathlib.Path(out['model_glb']).read_bytes()
                if len(raw)>1_500_000:raise ValueError('GLB excede 1,5MB; use o executor local.')
                result={'ok':True,'model_base64':base64.b64encode(raw).decode('ascii'),
                        'filename':'edificacao_modelo.glb','size_bytes':len(raw),
                        'fidelity':out['fidelity'],'warnings':out['warnings']}
                return JSONResponse(_response(mid,_tools_result(result)))
            if name=='preview_room':
                views_path=pathlib.Path(out['views_json'])
                views=json.loads(views_path.read_text(encoding='utf-8'))
                room_id=args.get('room_id') or next(iter(views))
                if room_id not in views:raise ValueError('Cômodo inexistente no projeto.')
                views_path.write_text(json.dumps({room_id:views[room_id]},ensure_ascii=False),encoding='utf-8')
                pngs=render_previews(out['model_glb'],str(views_path),dirname,480,360)['pngs']
                raw=pathlib.Path(pngs[0]).read_bytes()
                info={'ok':True,'room_id':room_id,'renderer':'CPU preview (not photorealistic)',
                      'fidelity':out['fidelity'],'warnings':out['warnings']}
                extra=[{'type':'image','mimeType':'image/png','data':base64.b64encode(raw).decode('ascii')}]
                return JSONResponse(_response(mid,_tools_result(info,extra)))
        return JSONResponse(_response(mid,_fail(ValueError('Nome de ferramenta desconhecido.'))))
    except Exception as exc:
        return JSONResponse(_response(mid,_fail(exc)))
