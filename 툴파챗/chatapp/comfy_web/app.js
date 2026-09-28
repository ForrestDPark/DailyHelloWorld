const $=id=>document.getElementById(id);let busy=false;
function esc(v){return String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]))}
function toast(message){const el=$("toast");el.textContent=message;el.classList.add("show");setTimeout(()=>el.classList.remove("show"),2600)}
function duration(sec){sec=Number(sec)||0;if(!sec)return "계산 중";const h=Math.floor(sec/3600),m=Math.ceil(sec%3600/60);return h?`약 ${h}시간 ${m}분`:`약 ${m}분`}
async function json(url,options={}){const r=await fetch(url,{credentials:"same-origin",...options});const data=await r.json().catch(()=>({}));if(!r.ok)throw new Error(data.detail||"요청에 실패했습니다");return data}
function render(data){
  $("runtime").textContent=data.comfy_label;$("lamp").classList.toggle("on",data.comfy_online);$("power").checked=!!data.comfy_online;$("power").disabled=!data.comfy_control_available||busy;
  $("runtime-note").textContent=data.comfy_online?"ComfyUI가 이미지 생성 요청을 받을 수 있습니다.":"ComfyUI가 꺼져 있어 생성 대기열이 진행되지 않습니다.";
  $("checked").textContent=new Date(data.checked_at).toLocaleTimeString("ko-KR",{hour:"2-digit",minute:"2-digit",second:"2-digit"});
  const jobs=data.active_jobs||[];$("active").innerHTML=jobs.length?jobs.map(j=>`<article class="job"><header><b>${esc(j.work)}</b><span>${Number(j.percent)||0}%</span></header><p>${esc(j.kind)} · ${esc(j.task)}</p><div class="progress"><i style="width:${Number(j.percent)||0}%"></i></div></article>`).join(""):`<p class="empty">현재 나툼 이미지 작업은 없습니다.</p>`;
  const q=data.queue||{};$("running-count").textContent=q.running_count||0;$("pending-count").textContent=q.pending_count||0;
  const rows=[...(q.running||[]).map(x=>({...x,state:"실행 중"})),...(q.pending||[]).map(x=>({...x,state:"대기"}))];
  $("queue").innerHTML=rows.length?rows.map(x=>`<article class="queue-item"><b>${x.state}</b><div><strong>${esc(x.output_prefix||x.prompt_id)}</strong><p>${esc(x.checkpoint||`${x.node_count}개 노드`)}</p></div></article>`).join(""):`<p class="empty">Comfy 대기열이 비어 있습니다.</p>`;
  $("interrupt").disabled=busy||!(q.running_count>0);$("clear").disabled=busy||!(q.pending_count>0);
  const b=data.backlog||{};$("backlog-state").textContent=b.ui_status_label||b.status||"대기 중";$("progress-bar").style.width=`${Number(b.percent)||0}%`;
  $("backlog-detail").textContent=b.running?`${b.current||"준비 중"} · ${b.current_image_job||"이미지 생성"} · 남은 시간 ${duration(b.eta_seconds)}`:`완료 ${b.display_completed||b.completed||0}편 · 실패 ${b.failed||0}편`;
  $("resume").disabled=busy||!!b.running;$("logs").textContent=data.log_tail||"기록된 Comfy 로그가 없습니다.";
}
async function refresh(){try{render(await json("/api/comfy-workspace/status"))}catch(e){toast(e.message)}}
async function act(url,options,message){if(busy)return;busy=true;try{const data=await json(url,options);toast(data.message||message);await refresh()}catch(e){toast(e.message)}finally{busy=false;await refresh()}}
$("refresh").onclick=refresh;
$("power").onchange=e=>act("/api/dating-sim/comfyui/runtime",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({enabled:e.target.checked})},"전원 상태를 바꿨습니다");
$("interrupt").onclick=()=>confirm("현재 생성 중인 한 장을 중단할까요? 나툼 일괄 작업은 다음 항목을 계속 시도할 수 있습니다.")&&act("/api/comfy-workspace/action",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({action:"interrupt"})},"중단 요청을 보냈습니다");
$("clear").onclick=()=>confirm("Comfy에 대기 중인 작업을 모두 비울까요?")&&act("/api/comfy-workspace/action",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({action:"clear_pending"})},"대기열을 비웠습니다");
$("resume").onclick=()=>act("/api/dating-sim/generate-missing-images",{method:"POST"},"미완성 이미지 작업을 시작했습니다");
refresh();setInterval(()=>{if(!document.hidden&&!busy)refresh()},3000);
