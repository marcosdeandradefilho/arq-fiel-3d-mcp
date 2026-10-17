"""Generate a single offline SVG editor for source-coordinate plan review.
Never inject source text as executable HTML: embed JSON as base64.
"""
import base64
import json
import math
import pathlib


HTML=r'''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>ArqFiel 3D · Revisão geométrica</title><style>
*{box-sizing:border-box}body{margin:0;font:14px system-ui,Arial;background:#eef1f4;color:#182535}header{padding:12px 18px;background:#162739;color:#fff}header strong{font-size:19px}
main{display:grid;grid-template-columns:minmax(0,3fr) minmax(300px,1fr);gap:12px;padding:12px;height:calc(100vh - 56px)}
#canvasbox{background:white;border-radius:10px;overflow:hidden;position:relative;min-height:340px;display:flex;align-items:center;justify-content:center}
svg{width:100%;height:100%;touch-action:none}aside{overflow:auto;background:white;border-radius:10px;padding:16px}
label{display:block;font-weight:600;margin-top:10px}input{width:100%;padding:9px;border:1px solid #b7bec8;border-radius:6px;margin-top:4px}
button{background:#20446a;color:white;border:0;border-radius:6px;padding:9px 11px;margin:5px 4px 5px 0;cursor:pointer}button:focus-visible{outline:3px solid orange}
.mode{background:#576b7a}.selected-mode{background:#078474}.hint{color:#536374;font-size:12px;line-height:1.45}
#segments{display:block;max-height:130px;overflow:auto;padding:8px;background:#f5f7f9;margin:10px 0;font-size:12px}
line{cursor:pointer;stroke:#9ea8b5;stroke-width:2;vector-effect:non-scaling-stroke}line.selected{stroke:#c17b12;stroke-width:4}circle,.poly{pointer-events:none}
@media(max-width:800px){main{grid-template-columns:1fr;grid-template-rows:minmax(320px,1fr) auto;height:auto}aside{max-height:none}}
</style></head><body><header><strong>ArqFiel 3D</strong> · Revisão e calibração assistida de planta</header>
<main><section id="canvasbox"><svg id="plan" role="img" aria-label="Linhas candidatas da planta"></svg></section><aside>
<strong>1. Escala</strong><div class="hint">Escolha Referência A e B, clique na planta nas duas extremidades de uma medida conhecida. Informe o comprimento real em metros.</div>
<button class="mode selected-mode" data-mode="a">Referência A</button><button class="mode" data-mode="b">Referência B</button>
<label>Referência A (origem)</label><input id="ra" readonly aria-label="Referência A">
<label>Referência B</label><input id="rb" readonly aria-label="Referência B">
<label>Comprimento real (m)</label><input id="meters" type="number" min="0.05" step="0.01" placeholder="Ex.: 4.00">
<hr><strong>2. Selecione as paredes</strong><p class="hint">Clique nas linhas em cinza para selecionar ou desmarcar. Desmarque cotas, eixos e desenhos de mobiliário.</p>
<div id="segments" role="status" aria-live="polite">Nenhuma parede selecionada.</div>
<hr><strong>3. Delimite os cômodos</strong><p class="hint">Escolha 'Novo cômodo', clique nos vértices do perímetro e finalize. Use somente vértices confirmados da planta.</p>
<label>Nome do cômodo</label><input id="roomname" value="Sala" placeholder="Nome do cômodo">
<button class="mode" data-mode="room">Novo cômodo / pontos</button><button id="finish">Concluir perímetro</button>
<button id="undo">Desfazer ponto</button><div id="roomlist" class="hint">Nenhum cômodo confirmado.</div>
<hr><strong>4. Confirmação</strong><label><input id="approved" type="checkbox" style="width:auto"> Aprovo esta seleção e as medidas informadas</label>
<p class="hint">Essa aprovação confirma o traçado que você revisou. Não comprova estrutura, obra construída, instalações ou aprovação técnica.</p>
<button id="export">Exportar seleção JSON</button><div id="msg" role="status" class="hint"></div>
</aside></main>
<script>
'use strict';
const encoded='__DATA__';const trace=JSON.parse(atob(encoded));
const lines=trace.lines||[];const svg=document.querySelector('#plan');const ns='http://www.w3.org/2000/svg';
const selected=new Set();const rooms=[];let poly=[];let mode='a';let ra=null,rb=null;
const pts=lines.flatMap(l=>[l.a,l.b]);
const minx=pts.length?Math.min(...pts.map(p=>p[0])):0,maxx=pts.length?Math.max(...pts.map(p=>p[0])):100;
const miny=pts.length?Math.min(...pts.map(p=>p[1])):0,maxy=pts.length?Math.max(...pts.map(p=>p[1])):100;
const pad=Math.max(maxx-minx,maxy-miny)*.08+5;
svg.setAttribute('viewBox',`${minx-pad} ${miny-pad} ${Math.max(10,maxx-minx)+pad*2} ${Math.max(10,maxy-miny)+pad*2}`);
function el(type,attrs,parent=svg){let e=document.createElementNS(ns,type);for(let [k,v] of Object.entries(attrs))e.setAttribute(k,v);parent.appendChild(e);return e}
const polyLayer=el('g',{'id':'polygons'});
for(const line of lines){let e=el('line',{x1:line.a[0],y1:line.a[1],x2:line.b[0],y2:line.b[1],'data-id':line.id});
 e.addEventListener('click',ev=>{if(mode==='walls'){ev.stopPropagation();toggle(line.id,e)}})}
function toggle(id,e){selected.has(id)?selected.delete(id):selected.add(id);e.classList.toggle('selected',selected.has(id));
 document.querySelector('#segments').textContent=selected.size?`${selected.size} parede(s): ${[...selected].join(', ')}`:'Nenhuma parede selecionada.'}
function redraw(){polyLayer.innerHTML='';for(const r of rooms){el('polygon',{points:r.polygon_source.map(p=>p.join(',')).join(' '),fill:'#0f9d8244',stroke:'#087b68','stroke-width':'3'},polyLayer)}
 if(poly.length){el('polyline',{points:poly.map(p=>p.join(',')).join(' '),fill:'none',stroke:'#1c73bd','stroke-width':'3'},polyLayer)} }
function srcPoint(ev){const p=svg.createSVGPoint();p.x=ev.clientX;p.y=ev.clientY;const mat=svg.getScreenCTM();const q=p.matrixTransform(mat.inverse());return [+q.x.toFixed(2),+q.y.toFixed(2)]}
svg.addEventListener('click',ev=>{if(mode==='walls')return;let point=srcPoint(ev);
 if(mode==='a'){ra=point;document.querySelector('#ra').value=point.join(', ');mode='b'}
 else if(mode==='b'){rb=point;document.querySelector('#rb').value=point.join(', ');mode='walls'}
 else if(mode==='room'){poly.push(point);redraw()} setMode(mode)});
function setMode(m){mode=m;for(const b of document.querySelectorAll('[data-mode]')) b.classList.toggle('selected-mode',b.dataset.mode===mode)}
for(const b of document.querySelectorAll('[data-mode]'))b.addEventListener('click',()=>setMode(b.dataset.mode));
// A separate button to select walls is provided, so selecting geometry never silently marks annotations as wall.
const selector=document.createElement('button');selector.textContent='Selecionar paredes';selector.className='mode';
selector.addEventListener('click',()=>setMode('walls'));document.querySelector('#segments').before(selector);
document.querySelector('#undo').onclick=()=>{poly.pop();redraw()};
document.querySelector('#finish').onclick=()=>{if(poly.length<3){alert('Informe ao menos três vértices.');return}
 rooms.push({id:'comodo_'+(rooms.length+1),name:document.querySelector('#roomname').value||'Cômodo',polygon_source:poly.slice()});poly=[];redraw();
 document.querySelector('#roomlist').textContent=rooms.map(r=>r.name).join('; ')};
document.querySelector('#export').onclick=()=>{const m=Number(document.querySelector('#meters').value);
 if(!ra||!rb||!Number.isFinite(m)||m<.05||m>100||!rooms.length||!document.querySelector('#approved').checked){
 document.querySelector('#msg').textContent='É necessário indicar escala, desenhar cômodos e marcar aprovação.';return}
 const obj={trace,reference_a:ra,reference_b:rb,length_m:m,rooms,wall_ids:[...selected],approval:true,
 derive_walls_from_rooms:true,wall_thickness_m:.15,ceiling_height_m:2.7,
 notes:'Paredes derivadas exclusivamente dos perímetros aprovados; linhas selecionadas ajudam na conferência, mas não são usadas nesse modo. Espessura e pé-direito requerem confirmação.'};
 const blob=new Blob([JSON.stringify(obj,null,2)],{type:'application/json'});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download='selecao-arqfiel.json';a.click();URL.revokeObjectURL(url);
 document.querySelector('#msg').textContent='Seleção exportada. Confira a espessura e o pé-direito antes da importação.';};
</script></body></html>'''


def create_review_editor(trace,output_html):
    if not isinstance(trace,dict) or not isinstance(trace.get('lines'),list) or len(trace['lines'])>1600:
        raise ValueError('Traçado não suportado.')
    out=pathlib.Path(output_html).expanduser().resolve();out.parent.mkdir(parents=True,exist_ok=True)
    payload=base64.b64encode(json.dumps(trace,ensure_ascii=False,separators=(',',':')).encode('utf-8')).decode('ascii')
    out.write_text(HTML.replace('__DATA__',payload),encoding='utf-8')
    return {'ok':True,'html':str(out),'lines':len(trace['lines']),
            'status':'interactive-review-required',
            'warning':'A aprovação dos traçados e medidas é humana. Browser local, sem upload externo.'}
