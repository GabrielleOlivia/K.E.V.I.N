'use strict';
// Browser controls affect ONLY simulated sensor sources on localhost.
const cards = new Map(), history = new Map();
let token = null, busy = false, commandPending = 0;
const el = (tag, cls, text) => {const e = document.createElement(tag);if(cls)e.className=cls;if(text!==undefined)e.textContent=text;return e;};
const $ = (id) => document.getElementById(id);
function note(message, error=false){$('control-status').textContent=message;$('control-status').className='control-status'+(error?' bad':'');}
async function command(payload){
 if(!token)throw Error('Simulation controls unavailable');
 commandPending++;
 try {
  const r=await fetch('/api/simulation',{method:'POST',headers:{'Content-Type':'application/json','X-KEVIN-Token':token},body:JSON.stringify(payload)});
  const body=await r.json();if(!r.ok)throw Error(body.error||'Control rejected');
  return body.simulation_control;
 }finally{commandPending--;}
}
function sourceLabel(data){return data.simulated?'SIMULATED':data.source?.startsWith('replay:')?'RECORDED REPLAY':data.source?'PHYSICAL INPUT':'NO INPUT';}
function makeCard(id){
 const c=el('article','card'),head=el('div','row'),name=el('h2',null,id.replaceAll('_',' ')),badge=el('span','badge');head.append(name,badge);
 const origin=el('p','origin'),value=el('div','number'),unit=el('div','unit'),detail=el('p','detail'),canvas=el('canvas','chart');
 const label=el('label','toggle'),toggle=el('input');toggle.type='checkbox';toggle.setAttribute('aria-label','Enable '+id+' simulation');label.append(toggle,el('span',null,'Enable synthetic stream'));
 toggle.addEventListener('change',async()=>{const intended=toggle.checked;try{await command({sensor_id:id,enabled:intended});note(id.replaceAll('_',' ')+(intended?' simulation enabled':' stream disabled; watch it become stale'));}catch(e){toggle.checked=!intended;note(e.message,true);}});
 const manual=el('div','manual'),mLabel=el('label',null,'Set a manual test signal'),mRow=el('div','manual-row'),readout=el('span',null,'—'),reset=el('button',null,'Auto waveform');reset.type='button';const slider=el('input');slider.type='range';slider.setAttribute('aria-label',id+' manual simulation value');
 mRow.append(readout,reset);manual.append(mLabel,mRow,slider,el('div','manual-note','Synthetic test values only · slider changes a simulation fixture'));
 slider.addEventListener('input',()=>{readout.textContent=slider.value+' '+(manual.dataset.unit||'');});
 slider.addEventListener('change',async()=>{const value=Number(slider.value);try{await command({action:'override',sensor_id:id,value});note('Manual synthetic '+id.replaceAll('_',' ')+' = '+value+' '+(manual.dataset.unit||''));}catch(e){note(e.message,true);}});
 reset.addEventListener('click',async()=>{try{await command({action:'override',sensor_id:id,value:null});note('Automatic synthetic waveform restored for '+id.replaceAll('_',' '));}catch(e){note(e.message,true);}});
 c.append(head,origin,value,unit,canvas,detail,label,manual);$('cards').append(c);
 const parts={c,badge,origin,value,unit,detail,canvas,label,toggle,manual,slider,readout,reset};cards.set(id,parts);history.set(id,[]);return parts;
}
function graph(canvas,points){
 const dpr=window.devicePixelRatio||1,w=Math.max(1,canvas.clientWidth*dpr),h=100*dpr;canvas.width=w;canvas.height=h;const ctx=canvas.getContext('2d');if(!ctx)return;ctx.clearRect(0,0,w,h);
 const valid=points.filter(p=>Number.isFinite(p));if(!valid.length)return;let low=Math.min(...valid),high=Math.max(...valid);if(low===high){low-=1;high+=1;}
 ctx.strokeStyle='#314762';ctx.beginPath();ctx.moveTo(0,h-12*dpr);ctx.lineTo(w,h-12*dpr);ctx.stroke();ctx.fillStyle='#8baccb';ctx.font=`${10*dpr}px system-ui`;ctx.fillText(high.toFixed(1),0,12*dpr);
 ctx.strokeStyle='#71dec9';ctx.lineWidth=2*dpr;ctx.beginPath();let drawing=false;
 points.forEach((p,i)=>{if(!Number.isFinite(p)){drawing=false;return;}const x=i/119*w,y=h-12*dpr-(p-low)/(high-low)*(h-32*dpr);if(!drawing){ctx.moveTo(x,y);drawing=true;}else ctx.lineTo(x,y);});ctx.stroke();
}
function updateControlState(ctrl){
 if(!ctrl){$('mode').textContent='PHYSICAL / REPLAY — read only';$('pause').disabled=true;$('reset-overrides').disabled=true;$('scenario').disabled=true;note('Only simulated inputs can be controlled.');return;}
 $('mode').textContent='SIMULATION ENABLED';$('pause').disabled=false;$('reset-overrides').disabled=false;$('scenario').disabled=false;
 if(document.activeElement!==$('scenario')&&!commandPending)$('scenario').value=ctrl.scenario;
 $('pause').textContent=ctrl.paused?'Resume all simulated streams':'Pause all simulated streams';$('pause').dataset.paused=String(ctrl.paused);
 for(const [id,c] of cards){
  const available=ctrl.available.includes(id);c.label.hidden=!available;c.manual.hidden=!available||!ctrl.limits?.[id];
  if(!available)continue;
  c.toggle.disabled=false;
  c.slider.disabled=false;
  c.toggle.checked=ctrl.enabled.includes(id);
  const limit=ctrl.limits[id];if(!limit)continue;
  c.manual.dataset.unit=limit.label;c.slider.min=limit.min;c.slider.max=limit.max;c.slider.step=limit.step;
  const isManual=Object.prototype.hasOwnProperty.call(ctrl.overrides,id);
  c.manual.querySelector('.manual-note').textContent=isManual?'Manual synthetic value active — press Auto waveform to restore':'Synthetic test values only · not physiological validation';
  if(document.activeElement!==c.slider&&!commandPending){const v=isManual?ctrl.overrides[id]:Math.min(limit.max,Math.max(limit.min,0));c.slider.value=v;c.readout.textContent=isManual?Number(v).toFixed(limit.step<1?1:0)+' '+limit.label:'Auto waveform';}
  c.reset.disabled=!isManual;
 }
}
$('pause').addEventListener('click',async()=>{const paused=$('pause').dataset.paused!=='true';try{await command({action:'pause',paused});note(paused?'All synthetic streams paused; watch sensor states time out':'Synthetic streams resumed');}catch(e){note(e.message,true);}});
$('scenario').addEventListener('change',async()=>{try{await command({action:'scenario',scenario:$('scenario').value});note('Fault timeline restarted for '+$('scenario').value+' scenario');}catch(e){note(e.message,true);}});
$('reset-overrides').addEventListener('click',async()=>{try{const ids=[...cards].filter(([id,c])=>!c.manual.hidden).map(([id])=>id);for(const id of ids)await command({action:'override',sensor_id:id,value:null});note('All synthetic waveforms restored');}catch(e){note(e.message,true);}});
async function poll(){
 if(busy)return;busy=true;const controller=new AbortController(),timeout=setTimeout(()=>controller.abort(),2000);
 try{
  const r=await fetch('/api/state',{cache:'no-store',signal:controller.signal});if(!r.ok)throw Error('host unavailable');const s=await r.json();token=s.simulation_control?.token||null;
  $('connection').textContent='Connected · '+new Date().toLocaleTimeString();$('connection').className='active';
  for(const [id,data] of Object.entries(s.channels)){
   const c=cards.get(id)||makeCard(id),v=data.value;c.badge.textContent=data.state;c.badge.className='badge '+(data.valid?'active':'bad');
   c.origin.textContent=sourceLabel(data);c.value.textContent=data.valid?(Array.isArray(v)?v.map(n=>Number(n).toFixed(3)).join(' · '):Number(v).toFixed(2)):'—';
   c.unit.textContent=data.unit+(Array.isArray(v)?' · graph: w component':'');c.detail.textContent=(data.reason||'Valid sample')+' | '+(data.age_s===null?'no sample':data.age_s.toFixed(2)+' s old')+' | '+data.calibration;
   const h=history.get(id);h.push(data.valid?(Array.isArray(v)?v[0]:v):null);if(h.length>120)h.shift();graph(c.canvas,h);
  }
  updateControlState(s.simulation_control);
  const d=s.derived.relative_rotation_deg;$('derived').textContent=d.valid?d.value.toFixed(2)+'°'+(d.simulated?' · SIMULATED':''):d.reason;
  $('counters').textContent=Object.entries(s.diagnostics).map(([k,v])=>k+': '+v).join(' · ')||'No diagnostics yet';
  $('events').textContent=s.events.slice(-12).reverse().map(e=>e.code+' — '+e.detail).join('\n')||'No events';
 }catch(e){token=null;$('connection').textContent='HOST DISCONNECTED — readings unavailable';$('connection').className='offline';
  $('pause').disabled=true;$('scenario').disabled=true;$('reset-overrides').disabled=true;
  for(const [id,c] of cards){c.value.textContent='—';c.badge.textContent='host offline';c.badge.className='badge bad';c.toggle.disabled=true;c.slider.disabled=true;c.reset.disabled=true;const h=history.get(id);h.push(null);if(h.length>120)h.shift();graph(c.canvas,h);}
 }finally{clearTimeout(timeout);busy=false;}
}
poll();setInterval(poll,250);
