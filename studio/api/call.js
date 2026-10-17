'use strict';
// Team-SSO-protected browser-to-MCP proxy. The backend Bearer key is server-side only.
const TOOLS=new Set(['extract_trace_source','calibrate_trace','suggest_rooms','reviewed_project','validate_project','export_glb','preview_room','plan_views']);
const BACKEND='https://arq-fiel-3d-mcp.vercel.app/api/mcp';
const MAX_REQUEST=3_300_000;
function json(res,status,body){res.setHeader('Cache-Control','no-store');res.setHeader('X-Content-Type-Options','nosniff');return res.status(status).json(body)}
module.exports=async function handler(req,res){
  res.setHeader('Allow','POST');
  if(req.method!=='POST')return json(res,405,{error:'Método não permitido.'});
  const origin=req.headers?.origin;
  const allowed=new Set(['https://arq-fiel-3d-studio.vercel.app', 'https://arq-fiel-studio.vercel.app']);
  if(process.env.VERCEL_URL)allowed.add('https://'+process.env.VERCEL_URL);
  if(process.env.VERCEL_PROJECT_PRODUCTION_URL)allowed.add('https://'+process.env.VERCEL_PROJECT_PRODUCTION_URL);
  if(origin && !allowed.has(origin))return json(res,403,{error:'Origem não permitida.'});
  let body=req.body;
  if(typeof body==='string'){try{body=JSON.parse(body)}catch{return json(res,400,{error:'JSON inválido.'})}}
  if(!body||typeof body!=='object'||Array.isArray(body)||!TOOLS.has(body.name)||!body.arguments||typeof body.arguments!=='object'||Array.isArray(body.arguments))return json(res,400,{error:'Ferramenta ou argumentos inválidos.'});
  if(Buffer.byteLength(JSON.stringify(body),'utf8')>MAX_REQUEST)return json(res,413,{error:'Envio grande demais.'});
  if(process.env.ARQFIEL_STUDIO_SSO_CONFIRMED!=='true')return json(res,503,{error:'Acesso privado ao Studio ainda não foi confirmado no Vercel.'});
  const key=process.env.ARQFIEL_MCP_API_KEY;
  if(!key)return json(res,503,{error:'Servidor ainda não configurado.'});
  try{
    const controller=new AbortController();const timeout=setTimeout(()=>controller.abort(),27000);
    let upstream;
    try{upstream=await fetch(BACKEND,{method:'POST',headers:{'Content-Type':'application/json','Accept':'application/json,text/event-stream',Authorization:'Bearer '+key},body:JSON.stringify({jsonrpc:'2.0',id:1,method:'tools/call',params:{name:body.name,arguments:body.arguments}}),signal:controller.signal})}finally{clearTimeout(timeout)}
    if(!upstream.ok)return json(res,502,{error:'MCP remoto indisponível ('+upstream.status+').'});
    const data=await upstream.json();
    if(data.error)return json(res,502,{error:typeof data.error.message==='string'?data.error.message:'Resposta MCP inválida.'});
    if(!data.result||!Array.isArray(data.result.content))return json(res,502,{error:'Formato MCP inesperado.'});
    const result=data.result;
    return json(res,200,{ok:!result.isError,content:result.content,structuredContent:result.structuredContent||null,isError:!!result.isError});
  }catch(err){return json(res,502,{error:err.name==='AbortError'?'MCP excedeu o tempo de resposta.':'Falha na comunicação com o MCP.'})}
};
