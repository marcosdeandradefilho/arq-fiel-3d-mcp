(function(root,factory){'use strict';const exposed=factory();if(typeof module==='object'&&module.exports)module.exports=exposed;else root.ArqMath=exposed})(typeof self!=='undefined'?self:this,function(){
 'use strict';
 const round=n=>Math.round(n*100000)/100000;
 function toMeters(point,scaled){if(!scaled?.source_origin||!(scaled.meters_per_source_unit>0))throw Error('Primeiro calibre a escala');return point.map((v,i)=>round((v-scaled.source_origin[i])*scaled.meters_per_source_unit))}
 function fromMeters(point,scaled){if(!scaled?.source_origin||!(scaled.meters_per_source_unit>0))throw Error('Primeiro calibre a escala');return point.map((v,i)=>round(v/scaled.meters_per_source_unit+scaled.source_origin[i]))}
 function isUsablePolygon(poly){if(!Array.isArray(poly)||poly.length<3)return false;let area=0;for(let i=0;i<poly.length;i++){const a=poly[i],b=poly[(i+1)%poly.length];if(!Array.isArray(a)||!Array.isArray(b)||a.length!==2||b.length!==2||!a.every(Number.isFinite)||!b.every(Number.isFinite))return false;area+=a[0]*b[1]-b[0]*a[1]}return Math.abs(area)>0.00001}
 function candidateRoom(c,scaled,i){if(!c||!Array.isArray(c.polygon_m)||!isUsablePolygon(c.polygon_m))throw Error('Região candidata inválida');return{id:'comodo_'+i,name:'Ambiente sugerido '+i,polygon_source:c.polygon_m.map(p=>fromMeters(p,scaled)),confirmed:false}}
 const defaultSizes={sofa:[1.8,.85,.85],dining_table:[1.6,.9,.75],bed:[1.9,1.4,.6],desk:[1.3,.65,.75],chair:[.55,.55,.85],cabinet:[1.2,.5,1.8]};
 function newFurniture(room,type){if(!room||!isUsablePolygon(room.polygon))throw Error('Cômodo inválido');if(!defaultSizes[type])throw Error('Tipo inválido');const n=room.polygon.length;const c=[0,1].map(k=>round(room.polygon.reduce((s,p)=>s+p[k],0)/n));return{id:'movel_'+Date.now(),room_id:room.id,type,center:c,size:[...defaultSizes[type]],rotation_deg:0,color:'#866a55'}}
 function assertReady(state){if(!state?.approved)throw Error('Aprovação explícita obrigatória');if(!state?.scaled)throw Error('Calibre antes');if(!Array.isArray(state.rooms)||!state.rooms.length)throw Error('Desenhe pelo menos um cômodo');if(!state.rooms.every(x=>isUsablePolygon(x.polygon_source)))throw Error('Corrija os polígonos')}
 return{toMeters,fromMeters,isUsablePolygon,candidateRoom,newFurniture,assertReady};
});
