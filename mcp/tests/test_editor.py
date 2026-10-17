import pathlib,sys
ROOT=pathlib.Path(__file__).parents[1]
sys.path.insert(0,str(ROOT/'runtime'))
from assisted_import import extract_trace
from review_editor import create_review_editor


def test_offline_editor_contains_review_ui_and_embedded_vectors(tmp_path):
    from PIL import Image,ImageDraw
    p=tmp_path/'plan.png';im=Image.new('RGB',(500,400),'white')
    ImageDraw.Draw(im).rectangle((30,40,430,340),outline='black',width=5)
    im.save(p)
    data=extract_trace(str(p))
    out=create_review_editor(data,str(tmp_path/'editor.html'))
    s=pathlib.Path(out['html']).read_text()
    assert 'Selecione as paredes' in s
    assert 'Referência A' in s
    assert 'Aprovo esta seleção' in s
    assert 'polygon_source' in s
    assert '<script' in s
    assert len(data['lines'])>=4


def test_editor_embeds_source_as_data_not_script(tmp_path):
    from review_editor import create_review_editor
    trace={'format':'dxf','source_file':'</script><script>alert(1)</script>',
           'lines':[{'id':'L1','a':[0,0],'b':[1,0],'layer':'</script>', 'origin':'test'}]}
    p=tmp_path/'x.html'
    create_review_editor(trace,str(p))
    body=p.read_text()
    assert '</script><script>alert(1)</script>' not in body
