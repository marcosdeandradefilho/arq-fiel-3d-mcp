"""Auditable tests for the opt-in Blender Cycles renderer, no GPU dependency."""
import ast
import json
import pathlib
import sys
from types import SimpleNamespace
import pytest

ROOT=pathlib.Path(__file__).parents[1]
sys.path.insert(0, str(ROOT/'runtime'))
from core import render_views
from render_pipeline import build_and_render_physical


def example():
    return json.loads((ROOT/'examples'/'sala-jantar-sintetica.json').read_text())


def test_blender_script_is_syntactically_valid():
    p=ROOT/'runtime'/'blender_render.py'
    ast.parse(p.read_text())


def test_blender_script_actually_uses_cycles_denoising_and_pbr():
    code=(ROOT/'runtime'/'blender_render.py').read_text()
    assert "scene.render.engine = 'CYCLES'" in code
    assert 'scene.cycles.use_denoising = True' in code
    assert "mat.use_nodes = True" in code
    assert "physically_based': True" in code
    assert "photographic_identity_guaranteed': False" in code


def test_build_and_render_refuses_unconfirmed_measurements(tmp_path):
    project=example()
    project['evidence']['scale_verified']=False
    with pytest.raises(ValueError,match='escala e dimensões'):
        build_and_render_physical(project, str(tmp_path))


def test_build_and_render_refuses_invalid_room_polygon(tmp_path):
    project=example()
    project['rooms'][0]['polygon']=[[0,0],[3,3],[0,3],[3,0]]
    with pytest.raises(ValueError,match='inválido'):
        build_and_render_physical(project,str(tmp_path))


def test_build_and_render_rejects_invalid_samples(tmp_path):
    for samples in (0, 15, 1025, True, 128.5):
        with pytest.raises(ValueError,match='16 e 1024'):
            build_and_render_physical(example(),str(tmp_path),samples=samples)


def test_render_views_no_blender_never_returns_false_success(tmp_path):
    model=tmp_path/'scene.glb'; model.write_bytes(b'glTF')
    views=tmp_path/'views.json';views.write_text('{"a": {}}')
    with pytest.raises(RuntimeError,match='Blender Cycles não instalado'):
        render_views(str(model),str(views),str(tmp_path/'out'),blender_executable=str(tmp_path/'blender'))


def test_render_views_checks_all_png_and_manifest(monkeypatch,tmp_path):
    import core
    renderer=tmp_path/'blender';renderer.write_text('fake binary')
    model=tmp_path/'model.glb';model.write_bytes(b'glTF')
    views=tmp_path/'views.json';views.write_text('{"sala":{},"jantar":{}}')
    dest=tmp_path/'pngs'
    png_signature=b'\x89PNG\r\n\x1a\n'
    def fake_run(args, **kwargs):
        dest.mkdir(exist_ok=True)
        for p in ['sala','jantar']:
            (dest/('comodo_'+p+'.png')).write_bytes(png_signature+b'0'*120)
        (dest/'render_manifest.json').write_text('{}')
        assert '--background' in args
        assert '--python' in args
        assert args[-1]=='96'
        return SimpleNamespace(returncode=0,stderr='')
    monkeypatch.setattr(core.subprocess,'run',fake_run)
    result=render_views(str(model),str(views),str(dest),str(renderer),96)
    assert result['ok']
    assert result['renderer'].startswith('Blender Cycles')
    assert len(result['pngs'])==2


def test_render_views_fails_when_png_missing(monkeypatch,tmp_path):
    import core
    blender=tmp_path/'blender';blender.write_text('')
    model=tmp_path/'model.glb';model.write_bytes(b'glTF')
    views=tmp_path/'views.json';views.write_text('{"sala":{},"jantar":{}}')
    def fake_run(args,**kwargs):return SimpleNamespace(returncode=0,stderr='')
    monkeypatch.setattr(core.subprocess,'run',fake_run)
    with pytest.raises(RuntimeError,match='0 de 2'):
        render_views(str(model),str(views),str(tmp_path/'out'),str(blender),64)


def test_one_call_pipeline_outputs_metric_scene_and_audited_renders(monkeypatch,tmp_path):
    import render_pipeline
    png_sig=b'\x89PNG\r\n\x1a\n'
    def fake_render(model,views,dir,**kwargs):
        p=pathlib.Path(dir);p.mkdir(parents=True,exist_ok=True)
        ims=[]
        for name in ('sala','jantar'):
            file=p/('comodo_'+name+'.png');file.write_bytes(png_sig+b'0'*200);ims.append(str(file))
        (p/'render_manifest.json').write_text('{"renderer":"Blender Cycles"}')
        return {'renderer':'Blender Cycles (path tracing + denoising)','pngs':ims}
    monkeypatch.setattr(render_pipeline,'render_views',fake_render)
    res=build_and_render_physical(example(),str(tmp_path),samples=64)
    assert res['render_validation']['rooms_rendered']==2
    assert res['render_validation']['photographic_identity_guaranteed'] is False
    assert pathlib.Path(res['model_glb']).read_bytes()[:4]==b'glTF'
    assert pathlib.Path(res['render_audit']).is_file()


def test_stdio_mcp_advertises_matching_runtime_version():
    import subprocess
    req=json.dumps({'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-11-25'}})+'\n'
    run=subprocess.run([sys.executable,str(ROOT/'runtime'/'server.py')],input=req,capture_output=True,text=True,timeout=10,check=True)
    response=json.loads(run.stdout.strip())
    assert response['result']['serverInfo']['version']=='0.3.1'
