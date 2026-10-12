'use strict';
const $=id=>document.getElementById(id), NS='http://www.w3.org/2000/svg';
let data, config, busy=false, tool='move', preview=null, comparison=null;
const labels={none:'No history',one:'Round 1',two:'Round 2',both:'Both rounds'};
function node(tag,attrs={},text){const n=document.createElementNS(NS,tag);Object.entries(attrs).forEach(([k,v])=>n.setAttribute(k,v));if(text!==undefined)n.textContent=text;return n;}
function escapeText(s){const n=document.createElement('span');n.textContent=String(s);return n.innerHTML;}
function notice(text){$('notice').textContent=text;$('notice').hidden=!text;}
async function api(path,body){const r=await fetch('/api/'+path,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const d=await r.json();if(!r.ok)throw Error(d.error||'Request failed');return d;}
function setBusy(value){busy=value;document.querySelectorAll('button,select').forEach(b=>b.disabled=value);if(config?.mode==='offline')$('benchmark').disabled=true;}
function actionLabel(a){if(!a)return 'No decision';const col=String.fromCharCode(65+a.x),row=9-a.y;return a.type==='move'?'Move to '+col+row:(a.orientation==='h'?'Horizontal':'Vertical')+' wall '+col+row;}
function renderBoard(){
  const svg=$('board');svg.replaceChildren();if(!data)return;
  const s=data.state, origin=40,pitch=62,size=54;
  svg.append(node('text',{x:320,y:19,'text-anchor':'middle',class:'goal'},'YOUR GOAL'));
  svg.append(node('text',{x:320,y:628,'text-anchor':'middle',class:'goal'},'OPPONENT GOAL'));
  for(let x=0;x<9;x++)svg.append(node('text',{x:origin+x*pitch+27,y:36,'text-anchor':'middle',class:'coordinate'},String.fromCharCode(65+x)));
  for(let y=0;y<9;y++){
    svg.append(node('text',{x:25,y:origin+y*pitch+32,'text-anchor':'middle',class:'coordinate'},9-y));
    for(let x=0;x<9;x++){
      const legal=data.legal_moves.some(a=>a.x===x&&a.y===y), active=legal&&tool==='move'&&!busy;
      const cell=node('rect',{x:origin+x*pitch,y:origin+y*pitch,width:size,height:size,rx:7,class:'cell'+(active?' legal':''),role:'button',tabindex:active?0:-1,'aria-label':'Square '+String.fromCharCode(65+x)+(9-y)+(active?', legal move':'')});
      const activate=()=>{if(active)humanMove({type:'move',x,y});};cell.addEventListener('click',activate);cell.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();activate();}});svg.append(cell);
    }
  }
  function wallShape(a,klass){
    return a.orientation==='h'?node('rect',{x:origin+a.x*pitch,y:origin+(a.y+1)*pitch-8,width:116,height:8,rx:3,class:klass})
      :node('rect',{x:origin+(a.x+1)*pitch-8,y:origin+a.y*pitch,width:8,height:116,rx:3,class:klass});
  }
  s.walls.forEach(w=>svg.append(wallShape(w,'wall')));
  if(tool!=='move'&&s.turn===0&&s.winner===null&&!busy){
    const ghost=node('g');svg.append(ghost);
    for(let y=0;y<8;y++)for(let x=0;x<8;x++){
      const target=node('circle',{cx:origin+(x+1)*pitch-4,cy:origin+(y+1)*pitch-4,r:12,class:'wall-target',role:'button',tabindex:0,'aria-label':(tool==='h'?'Horizontal':'Vertical')+' wall '+String.fromCharCode(65+x)+(9-y)});
      const a={type:'wall',x,y,orientation:tool};
      target.addEventListener('mouseenter',()=>ghost.replaceChildren(wallShape(a,'preview-ghost')));
      target.addEventListener('mouseleave',()=>ghost.replaceChildren());
      target.addEventListener('focus',()=>ghost.replaceChildren(wallShape(a,'preview-ghost')));
      target.addEventListener('blur',()=>ghost.replaceChildren());
      target.addEventListener('click',()=>humanMove(a));
      target.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();humanMove(a);}});
      svg.append(target);
    }
  }
  s.pawns.forEach((p,i)=>{
    const cx=origin+p[0]*pitch+27,cy=origin+p[1]*pitch+27;
    svg.append(node('circle',{cx,cy,r:20,fill:i===0?'#a8e4ca':'#efa78e',class:'pawn'}));
    svg.append(node('circle',{cx,cy:cy-2,r:8,fill:i===0?'#335f48':'#844932',class:'pawn'}));
  });
  if(preview){
    const a=preview.action;
    if(a.type==='wall')svg.append(wallShape(a,'preview-wall'));
    else{
      const p=s.pawns[1];
      svg.append(node('line',{x1:origin+p[0]*pitch+27,y1:origin+p[1]*pitch+27,x2:origin+a.x*pitch+27,y2:origin+a.y*pitch+27,class:'preview-move'}));
      svg.append(node('circle',{cx:origin+a.x*pitch+27,cy:origin+a.y*pitch+27,r:23,class:'preview-move'}));
    }
  }
}
function render(){
  const s=data.state;
  $('turn').textContent=s.winner===0?'You won. Your next opponent remembers.':s.winner===1?'Opponent wins. Try a different approach.':s.turn===0?'Your turn':busy?'Opponent is deciding…':'Opponent turn';
  $('ply').textContent='Move '+(s.ply+1);
  $('your-walls').textContent=s.remaining[0]+' walls';$('ai-walls').textContent=s.remaining[1]+' walls';
  $('distances').textContent='Shortest routes: you '+data.distances[0]+' / opponent '+data.distances[1];
  $('round-number').textContent=String(data.matches.length+1).padStart(2,'0');$('saved-count').textContent=data.matches.length;
  $('condition').value=data.condition;$('retry-ai').hidden=s.turn!==1||s.winner!==null;
  const recent=data.matches.slice(-2);
  $('memory').className='memory'+(recent.length?'':' empty');
  if(!recent.length)$('memory').textContent='No saved history yet. Finish a match, or explicitly save an unfinished round.';
  else $('memory').innerHTML=recent.map((h,i)=>'<div class="memory-round"><strong>Round '+(i+1)+' · '+h.player_turns+' turns</strong><span class="history-tag">'+escapeText(h.result)+'</span><p>Route: '+escapeText(h.preferred_lane)+' · Left moves: '+h.left_moves+' · Right moves: '+h.right_moves+'</p><p>'+h.walls_placed+' walls · '+(h.first_wall_turn?'First wall on turn '+h.first_wall_turn:'No wall placed')+'</p></div>').join('');
  if(data.last_decision){const d=data.last_decision;$('decision-reason').textContent=d.reason;$('decision-source').textContent=d.source==='qwen'?'QWEN':'OFFLINE';$('decision-time').textContent=(d.latency_ms/1000).toFixed(2)+' s · '+actionLabel(d.action);$('decision-history').textContent=d.history_count+' saved round(s)';}
  else{$('decision-reason').textContent='Make your first move to hear from your opponent.';$('decision-source').textContent='—';$('decision-time').textContent='—';$('decision-history').textContent='—';}
  renderBoard();
}
async function opponent(){
  if(data.state.turn!==1||data.state.winner!==null)return;
  render();data=await api('ai',{revision:data.revision});render();
}
async function humanMove(action){
  if(busy)return;setBusy(true);notice('');preview=null;
  try{data=await api('move',{action,revision:data.revision});render();await opponent();}
  catch(e){notice(e.message);}
  finally{setBusy(false);render();}
}
document.querySelectorAll('[data-tool]').forEach(b=>b.onclick=()=>{tool=b.dataset.tool;document.querySelectorAll('[data-tool]').forEach(x=>x.classList.toggle('active',x===b));$('board-hint').textContent=tool==='move'?'Click a highlighted square. Reach the top row to win.':'Click a glowing intersection to place a wall. Invalid placements are rejected.';renderBoard();});
async function restart(save){
  if(busy)return;setBusy(true);
  try{data=await api('new',{save_partial:save});preview=null;comparison=null;$('comparison').innerHTML=Object.values(labels).map(s=>'<div class="placeholder">'+s+'</div>').join('');notice('');render();}
  catch(e){notice(e.message);}finally{setBusy(false);render();}
}
$('new-game').onclick=()=>restart(false);$('save-round').onclick=()=>restart(true);
$('retry-ai').onclick=async()=>{setBusy(true);try{await opponent();notice('');}catch(e){notice(e.message);}finally{setBusy(false);render();}};
$('condition').onchange=async()=>{try{data=await api('condition',{condition:$('condition').value});render();}catch(e){notice(e.message);}};
$('reset-memory').onclick=async()=>{if(!confirm('Clear your saved rounds and restart this match?'))return;try{data=await api('reset-memory',{});preview=null;comparison=null;$('comparison').innerHTML=Object.values(labels).map(s=>'<div class="placeholder">'+s+'</div>').join('');render();}catch(e){notice(e.message);}};
$('compare').onclick=async()=>{
  setBusy(true);notice('');$('compare').textContent='Comparing…';
  try{
    comparison=await api('compare',{});preview=null;
    $('comparison').replaceChildren();
    comparison.rows.forEach((r,i)=>{
      const card=document.createElement('article');card.className='comparison-card';
      const h=document.createElement('h3');h.textContent=labels[r.condition];card.append(h);
      const small=document.createElement('small');small.textContent=r.error?'REQUEST FAILED':r.history_count+' saved round(s) · '+r.source.toUpperCase();card.append(small);
      const a=document.createElement('div');a.className='action';a.textContent=r.error?'No recommendation':actionLabel(r.action);card.append(a);
      const p=document.createElement('p');p.textContent=r.error||r.reason;card.append(p);
      if(!r.error){
        const timing=document.createElement('small');timing.textContent=(r.latency_ms/1000).toFixed(2)+' s response';card.append(timing);
        const b=document.createElement('button');b.textContent='Highlight move';b.onclick=()=>{if(data.revision!==comparison.revision){notice('The board has changed. Compare decisions again before highlighting.');return;}preview=r;document.querySelectorAll('.comparison-card').forEach(c=>c.classList.toggle('selected',c===card));renderBoard();};card.append(b);
      }$('comparison').append(card);
    });
    $('comparison-note').textContent='Four requests finished in '+(comparison.wall_ms/1000).toFixed(2)+' s. '+comparison.note+(config.mode==='offline'?' Offline comparisons use the same CPU baseline and do not demonstrate adaptation.':'');
  }catch(e){notice(e.message);}finally{$('compare').textContent='Compare decisions ↗';setBusy(false);render();}
};
$('benchmark').onclick=async()=>{
  setBusy(true);notice('');$('benchmark').textContent='Running…';
  try{
    const r=await api('benchmark',{concurrency:Number($('concurrency').value)});
    const metrics=[[(r.successes+'/'+r.concurrency),'Successful requests'],[r.decisions_per_second,'Decisions / second'],[r.completion_tokens_per_second,'Output tokens / second'],[r.p50_ms===null?'—':(r.p50_ms/1000).toFixed(2)+' s','Median decision latency'],[r.p95_ms===null?'—':(r.p95_ms/1000).toFixed(2)+' s','p95 decision latency']];
    const kv=r.peak_metrics['vllm:kv_cache_usage_perc']??r.peak_metrics['vllm:gpu_cache_usage_perc'];
    if(kv!==undefined)metrics.push([(kv*100).toFixed(1)+'%','Peak KV cache usage']);
    const running=r.peak_metrics['vllm:num_requests_running'];if(running!==undefined)metrics.push([running,'Peak running requests']);
    $('benchmark-results').replaceChildren();
    metrics.forEach(([v,l])=>{const m=document.createElement('div');m.className='metric';const strong=document.createElement('strong');strong.textContent=v;const span=document.createElement('span');span.textContent=l;m.append(strong,span);$('benchmark-results').append(m);});
    if(r.errors.length)notice(r.failures+' requests failed: '+r.errors[0]);
  }catch(e){notice(e.message);}finally{$('benchmark').textContent='Run benchmark';setBusy(false);}
};
async function start(){
  try{data=await api('state');render();config=await api('config');
    $('connection').className='connection'+(config.connected?' connected':'');
    $('connection').replaceChildren();$('connection').append(document.createElement('i'),document.createTextNode(config.mode==='offline'?'OFFLINE / CPU BASELINE':config.connected?'QWEN / GPU CONNECTED':'QWEN / DISCONNECTED'));
    if(config.mode==='offline')notice('Offline mode: playable CPU opponent. No GPU requests, no memory-based adaptation. Connect Qwen for the experiment.');
    else if(!config.connected)notice(config.error);
    setBusy(false);
  }catch(e){notice(e.message);}
}start();
