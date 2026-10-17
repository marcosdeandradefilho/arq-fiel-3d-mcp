'use strict';
// Readiness is determined by a real authenticated MCP handshake, not the presence of environment variables.
const url='https://arq-fiel-3d-mcp.vercel.app/api/mcp';
const fixed={name:'ArqFiel Studio',version:'0.1.1',backend:'ArqFiel 3D MCP v0.2.1',features:['calibração','revisão manual','GLB','prévia geométrica'],requires_human_approval:true};
module.exports=async function handler(req,res){
 res.setHeader('Cache-Control','no-store');
 if(req.method!=='GET')return res.status(405).json({error:'Método não permitido.'});
 const configured=process.env.ARQFIEL_STUDIO_SSO_CONFIRMED==='true'&&!!process.env.ARQFIEL_MCP_API_KEY;
 if(!configured)return res.status(200).json({...fixed,ready:false,reason:'Configuração privada ainda incompleta.'});
 const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),6000);
 try{
  const upstream=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json','Accept':'application/json,text/event-stream',Authorization:'Bearer '+process.env.ARQFIEL_MCP_API_KEY},body:JSON.stringify({jsonrpc:'2.0',id:1,method:'tools/list'}),signal:controller.signal});
  if(!upstream.ok){const reason=upstream.status===401?'A chave de autenticação do Studio não coincide com a do MCP.':`O motor MCP respondeu HTTP ${upstream.status}.`;return res.status(200).json({...fixed,ready:false,reason})}
  const data=await upstream.json();
  if(!Array.isArray(data?.result?.tools))return res.status(200).json({...fixed,ready:false,reason:'O MCP não retornou sua lista de ferramentas.'});
  return res.status(200).json({...fixed,ready:true,tools:data.result.tools.length});
 }catch{return res.status(200).json({...fixed,ready:false,reason:'Não foi possível verificar o motor MCP.'})}
 finally{clearTimeout(timer)}
};
