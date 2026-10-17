import os,sys,pathlib,json,base64
ROOT=pathlib.Path(__file__).parents[1]
sys.path.insert(0,str(ROOT))
from fastapi.testclient import TestClient
from api.index import app

def example():return json.loads((ROOT/'examples'/'sala-jantar-sintetica.json').read_text())


def request_tool(client,name,args=None,token='secret'):
    return client.post('/api/mcp',headers={'Authorization':f'Bearer {token}', 'Accept':'application/json, text/event-stream'},json={'jsonrpc':'2.0','id':17,'method':'tools/call','params':{'name':name,'arguments':args or {}}})


def test_cloud_refuses_unauthenticated(monkeypatch):
    monkeypatch.setenv('ARQFIEL_MCP_API_KEY','secret')
    client=TestClient(app)
    assert client.post('/api/mcp',json={'jsonrpc':'2.0','id':1,'method':'tools/list'}).status_code==401
    assert client.post('/api/mcp',headers={'Authorization':'Bearer wrong'},json={'jsonrpc':'2.0','id':1,'method':'tools/list'}).status_code==401


def test_cloud_tool_manifest_excludes_filesystem_methods(monkeypatch):
    monkeypatch.setenv('ARQFIEL_MCP_API_KEY','secret')
    client=TestClient(app)
    r=client.post('/api/mcp',headers={'Authorization':'Bearer secret'},json={'jsonrpc':'2.0','id':1,'method':'tools/list'})
    assert r.status_code==200
    names={x['name'] for x in r.json()['result']['tools']}
    assert {'validate_project','calibrate_trace','reviewed_project','preview_room','export_glb','extract_trace_source'} <= names
    assert 'render_views' not in names
    assert 'inspect_source' not in names


def test_cloud_validation_request_success(monkeypatch):
    monkeypatch.setenv('ARQFIEL_MCP_API_KEY','secret')
    response=request_tool(TestClient(app),'validate_project',{'project':example()})
    assert response.status_code==200
    assert response.json()['result']['structuredContent']['ok']


def test_cloud_export_real_glb_base64(monkeypatch):
    monkeypatch.setenv('ARQFIEL_MCP_API_KEY','secret')
    response=request_tool(TestClient(app),'export_glb',{'project':example()})
    assert response.status_code==200,response.text[:500]
    res=response.json()['result']['structuredContent']
    assert base64.b64decode(res['model_base64'])[:4]==b'glTF'
    assert res['fidelity']=='plant-validated-not-as-built'


def test_cloud_preview_room_returns_mcp_image(monkeypatch):
    monkeypatch.setenv('ARQFIEL_MCP_API_KEY','secret')
    response=request_tool(TestClient(app),'preview_room',{'project':example(),'room_id':'jantar'})
    assert response.status_code==200,response.text[:300]
    content=response.json()['result']['content']
    img=next((i for i in content if i['type']=='image'),None)
    assert img and img['mimeType']=='image/png'
    assert base64.b64decode(img['data'])[:8]==b'\x89PNG\r\n\x1a\n'


def test_cloud_source_bytes_pdf(monkeypatch):
    import fitz
    monkeypatch.setenv('ARQFIEL_MCP_API_KEY','secret')
    doc=fitz.open();p=doc.new_page();p.draw_line((10,20),(300,20));data=doc.tobytes()
    res=request_tool(TestClient(app),'extract_trace_source',{'source_base64':base64.b64encode(data).decode(),'extension':'.pdf'})
    assert res.status_code==200
    assert res.json()['result']['structuredContent']['format']=='pdf'


def test_cloud_get_health_no_secret(monkeypatch):
    monkeypatch.delenv('ARQFIEL_MCP_API_KEY',raising=False)
    c=TestClient(app)
    assert c.get('/api/health').json()['mcp_auth_configured'] is False
    assert c.post('/api/mcp',json={'jsonrpc':'2.0','id':1,'method':'tools/list'}).status_code==503
