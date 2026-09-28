const $=id=>document.getElementById(id);let busy=false,currentImage=null,selectedKeywords=[],currentHistory=[],currentHistoryIndex=0,modelCatalog=[];
const KEYWORDS={
  "표정":["gentle smile","bright smile","thoughtful expression","surprised expression","calm gaze"],
  "구도":["close-up portrait","waist-up shot","full body shot","over-the-shoulder composition","candid side profile"],
  "빛":["golden hour lighting","soft window light","cinematic night lighting","overcast soft light","warm indoor light"],
  "장소":["quiet bookstore","rainy street","cozy cafe","riverside path","sunlit library"],
  "품질":["natural symmetrical eyes","realistic skin texture","anatomically correct hands","sharp focus","cinematic depth of field"]
};
const CIVITAI_2805532_PROMPT="editorial studio portrait, adult Japanese woman, cream knit sweater dress, seated three-quarter pose, hand near chin, soft neutral seamless background, diffused window daylight, realistic natural skin texture, individual hair strands, sharp symmetrical eyes with natural catchlights, subtle natural makeup, shallow depth of field, professional fashion photography";
function applyPreset(name){
  if(name!=="civitai-2805532"){$("preset-note").textContent="";return}
  const values={"setting-width":512,"setting-height":768,"setting-steps":30,"setting-cfg":7,"setting-sampler":"dpmpp_2m","setting-scheduler":"karras","setting-denoise":1,"setting-hires-scale":1.5,"setting-hires-steps":10,"setting-hires-denoise":0.28};
  Object.entries(values).forEach(([id,v])=>$(id).value=v);
  $("prompt-editor").value=CIVITAI_2805532_PROMPT;
  $("preset-note").textContent="원본 메타데이터(512×768·30 steps·CFG 7)에 1.5배 디테일 보정을 더합니다. 흐릿한 원작 latent 혼합 없이 생성합니다.";
}
function esc(v){return String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]))}
function toast(message){const el=$("toast");el.textContent=message;el.classList.add("show");setTimeout(()=>el.classList.remove("show"),2600)}
function duration(sec){sec=Number(sec)||0;if(!sec)return "계산 중";const h=Math.floor(sec/3600),m=Math.ceil(sec%3600/60);return h?`약 ${h}시간 ${m}분`:`약 ${m}분`}
function openModel(model){
  const dialog=$("model-dialog");$("model-name").textContent=model.name;
  $("model-badges").innerHTML=`<span>${esc(model.family)}</span><span class="${model.installed?"installed":"not-installed"}">${model.installed?"설치됨":"미설치"}</span>${model.installed_file?`<span>${esc(model.installed_file)}</span>`:""}`;
  $("model-summary").textContent=model.summary;$("model-best").innerHTML=(model.best_for||[]).map(item=>`<li>${esc(item)}</li>`).join("");
  $("model-caution").textContent=model.caution;$("model-link").href=model.url;dialog.showModal();
}
function renderCatalog(data){
  modelCatalog=data.models||[];const installed=modelCatalog.filter(model=>model.installed).length;
  $("model-count").textContent=`${modelCatalog.length}개 · 설치 ${installed}개`;
  $("model-catalog").innerHTML=modelCatalog.map((model,index)=>`<button type="button" class="model-card" data-model-index="${index}"><span class="model-card-top"><b>${esc(model.name)}</b><i class="${model.installed?"installed":""}">${model.installed?"설치됨":"미설치"}</i></span><small>${esc(model.family)}</small><p>${esc(model.summary)}</p><span class="model-more">한글 설명 보기 ›</span></button>`).join("");
  document.querySelectorAll("[data-model-index]").forEach(button=>button.onclick=()=>openModel(modelCatalog[Number(button.dataset.modelIndex)]));
  const animation=data.animation||{},ready=!!animation.motion_ready;
  $("gif-badge").textContent=ready?"바로 사용 가능":"설치 필요";$("gif-badge").classList.toggle("ready",ready);
  $("gif-summary").textContent=animation.summary||"GIF 지원 상태를 확인하지 못했습니다.";
  $("gif-missing").innerHTML=(animation.missing||[]).map(item=>`<li>${esc(item)}</li>`).join("");
  $("gif-video-helper").href=animation.docs?.video_helper||"#";$("gif-animatediff").href=animation.docs?.animatediff||"#";
}
async function loadCatalog(){try{renderCatalog(await json("/api/comfy-workspace/models"))}catch(e){$("model-catalog").innerHTML=`<p class="error">${esc(e.message)}</p>`;toast(e.message)}}
function renderKeywords(){
  $("keyword-groups").innerHTML=Object.entries(KEYWORDS).map(([group,items])=>`<fieldset><legend>${esc(group)}</legend>${items.map(item=>`<button type="button" class="keyword${selectedKeywords.includes(item)?" on":""}" data-keyword="${esc(item)}">${esc(item)}</button>`).join("")}</fieldset>`).join("");
  $("selected-keywords").innerHTML=selectedKeywords.length?selectedKeywords.map(item=>`<button type="button" data-remove-keyword="${esc(item)}">${esc(item)} ×</button>`).join(""):`<span>선택한 키워드가 없습니다.</span>`;
  document.querySelectorAll("[data-keyword]").forEach(button=>button.onclick=()=>{const value=button.dataset.keyword;if(!selectedKeywords.includes(value))selectedKeywords.push(value);renderKeywords()});
  document.querySelectorAll("[data-remove-keyword]").forEach(button=>button.onclick=()=>{selectedKeywords=selectedKeywords.filter(value=>value!==button.dataset.removeKeyword);renderKeywords()});
}
function value(id,fallback){const n=Number($(id).value);return Number.isFinite(n)?n:fallback}
async function openPreview(button){
  const dialog=$("preview-dialog"),img=$("preview-full");selectedKeywords=[];
  img.src=button.dataset.url;img.alt=`${button.dataset.work} 생성 이미지`;$("preview-caption").textContent=`${button.dataset.work} · ${button.dataset.file}`;
  $("preview-references").innerHTML='<p class="hint">생성 이력을 불러오는 중입니다.</p>';$("editor-status").textContent="";dialog.showModal();
  await loadImageDetail(button.dataset.work,button.dataset.file,button.dataset.url,true);
}
async function loadImageDetail(work,file,url,resetHistory=false){
  currentImage={work,file};
  try{
    const detail=await json(`/api/comfy-workspace/image-detail?work=${encodeURIComponent(currentImage.work)}&file=${encodeURIComponent(currentImage.file)}`);
    if(resetHistory){currentHistory=detail.history||[];currentHistoryIndex=Math.max(0,currentHistory.findIndex(item=>item.filename===file))}
    const shown=currentHistory[currentHistoryIndex]||detail.preview||{filename:file,url};currentImage.file=shown.filename||file;
    $("preview-full").src=shown.url||url;$("preview-full").alt=`${work} 생성 이미지`;$("preview-caption").textContent=`${work} · ${currentImage.file}`;
    $("history-position").textContent=currentHistory.length?`${currentHistoryIndex+1} / ${currentHistory.length}`:"1 / 1";
    $("history-prev").disabled=currentHistory.length<2;$("history-next").disabled=currentHistory.length<2;
    currentImage.key=detail.image_key;$("prompt-editor").value=detail.prompt||"";$("effective-prompt").textContent=detail.effective_prompt||"기록 없음";
    const refs=detail.references||[];$("preview-references").innerHTML=refs.length?refs.map(ref=>`<figure><img src="${esc(ref.url)}" alt="${esc(ref.name)}"><figcaption>${esc(ref.name)}</figcaption></figure>`).join(""):'<p class="hint">이 이미지는 참조 이미지 없이 생성되었습니다.</p>';
    const s=detail.settings||{};$("setting-preset").value="custom";$("preset-note").textContent="";$("setting-width").value=s.width||512;$("setting-height").value=s.height||768;$("setting-steps").value=s.steps||25;$("setting-cfg").value=s.cfg||7;$("setting-sampler").value=s.sampler||"dpmpp_2m";$("setting-scheduler").value=s.scheduler||"karras";$("setting-denoise").value=s.denoise??1;$("setting-hires-scale").value=s.hires_scale||1;$("setting-hires-steps").value=s.hires_steps||10;$("setting-hires-denoise").value=s.hires_denoise||0.28;
    renderKeywords();
  }catch(e){$("preview-references").innerHTML=`<p class="error">${esc(e.message)}</p>`}
}
async function moveHistory(delta){
  if(currentHistory.length<2)return;currentHistoryIndex=(currentHistoryIndex+delta+currentHistory.length)%currentHistory.length;
  const item=currentHistory[currentHistoryIndex],work=currentImage.work;await loadImageDetail(work,item.filename,item.url,false);
}
async function json(url,options={}){const r=await fetch(url,{credentials:"same-origin",...options});const data=await r.json().catch(()=>({}));if(!r.ok)throw new Error(data.detail||"요청에 실패했습니다");return data}
function render(data){
  $("runtime").textContent=data.comfy_label;$("lamp").classList.toggle("on",data.comfy_online);$("power").checked=!!data.comfy_online;$("power").disabled=!data.comfy_control_available||busy;
  $("runtime-note").textContent=data.comfy_online?"ComfyUI가 이미지 생성 요청을 받을 수 있습니다.":"ComfyUI가 꺼져 있어 생성 대기열이 진행되지 않습니다.";
  $("checked").textContent=new Date(data.checked_at).toLocaleTimeString("ko-KR",{hour:"2-digit",minute:"2-digit",second:"2-digit"});
  const jobs=data.active_jobs||[];$("active").innerHTML=jobs.length?jobs.map(j=>`<article class="job"><header><b>${esc(j.work)}</b><span>${Number(j.percent)||0}%</span></header>${j.preview?`<button class="live-preview" data-url="${esc(j.preview.url)}" data-work="${esc(j.work)}" data-file="${esc(j.preview.filename)}"><img src="${esc(j.preview.url)}" alt="${esc(j.work)} 최신 생성 결과"><span><b>방금 완성된 이미지</b><small>눌러서 크게 보기</small></span></button>`:`<div class="preview-wait"><span>이미지 생성 중</span><small>첫 결과가 저장되면 여기에 바로 나타납니다.</small></div>`}<p>${esc(j.kind)} · ${esc(j.task)}</p><div class="progress"><i style="width:${Number(j.percent)||0}%"></i></div></article>`).join(""):`<p class="empty">현재 나툼 이미지 작업은 없습니다.</p>`;
  document.querySelectorAll(".live-preview").forEach(button=>button.onclick=()=>openPreview(button));
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
$("add-keyword").onclick=()=>{const input=$("custom-keyword"),keyword=input.value.trim();if(keyword&&!selectedKeywords.includes(keyword)){selectedKeywords.push(keyword);input.value="";renderKeywords()}};
$("setting-preset").onchange=e=>applyPreset(e.target.value);
$("image-editor").onsubmit=async event=>{
  event.preventDefault();if(!currentImage?.key||busy)return;
  busy=true;const submit=event.submitter;submit.disabled=true;$("editor-status").textContent="재생성 요청을 전달하는 중입니다.";
  const preset=$("setting-preset").value;const settings={width:value("setting-width",512),height:value("setting-height",768),steps:value("setting-steps",25),cfg:value("setting-cfg",7),sampler:$("setting-sampler").value,scheduler:$("setting-scheduler").value,denoise:value("setting-denoise",1),hires_scale:value("setting-hires-scale",1),hires_steps:value("setting-hires-steps",10),hires_denoise:value("setting-hires-denoise",0.28)};
  try{
    const noRefs=preset==="civitai-2805532"?"&no_references=true":"";await json(`/api/dating-sim/scenario-tree/generate-images?story_id=${encodeURIComponent(`work:${currentImage.work}`)}&force_key=${encodeURIComponent(currentImage.key)}${noRefs}`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({prompt_override:$("prompt-editor").value.trim(),keywords:selectedKeywords,settings})});
    $("editor-status").textContent="재생성을 시작했습니다. 현재 작업에서 진행률과 새 결과를 확인할 수 있습니다.";toast("수정한 설정으로 재생성을 시작했습니다");
  }catch(e){$("editor-status").textContent=e.message;toast(e.message)}finally{busy=false;submit.disabled=false;await refresh()}
};
$("preview-close").onclick=()=>$("preview-dialog").close();
$("model-close").onclick=()=>$("model-dialog").close();
$("model-dialog").onclick=e=>{if(e.target===$("model-dialog"))$("model-dialog").close()};
const resultImage=$("preview-full"),resultStage=document.createElement("div"),historyPrev=document.createElement("button"),historyNext=document.createElement("button"),historyPosition=document.createElement("p");
resultStage.className="result-stage";historyPrev.id="history-prev";historyPrev.type="button";historyPrev.setAttribute("aria-label","이전 생성물");historyPrev.textContent="‹";historyNext.id="history-next";historyNext.type="button";historyNext.setAttribute("aria-label","다음 생성물");historyNext.textContent="›";historyPosition.id="history-position";
resultImage.before(resultStage);resultStage.append(historyPrev,resultImage,historyNext);resultStage.after(historyPosition);
historyPrev.onclick=()=>moveHistory(1);historyNext.onclick=()=>moveHistory(-1);
$("preview-dialog").onclick=e=>{if(e.target===$("preview-dialog"))$("preview-dialog").close()};
document.addEventListener("keydown",e=>{if(!$("preview-dialog").open)return;if(e.key==="ArrowLeft")moveHistory(1);if(e.key==="ArrowRight")moveHistory(-1)});
loadCatalog();refresh();setInterval(()=>{if(!document.hidden&&!busy)refresh()},3000);
