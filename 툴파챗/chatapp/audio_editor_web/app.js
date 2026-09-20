const $ = id => document.getElementById(id);
const audio = $("audio"), canvas = $("waveform"), ctx = canvas.getContext("2d");
const WINDOW_SECONDS = 30;
let sourceFile = null, objectUrl = null, duration = 0, peaks = [], cuts = [], splits = [];
let viewportStart = 0, drag = null;

function formatTime(value, tenths = true) {
  const safe = Math.max(0, Number(value) || 0), minutes = Math.floor(safe / 60), seconds = safe - minutes * 60;
  return `${String(minutes).padStart(2,"0")}:${tenths ? seconds.toFixed(1).padStart(4,"0") : String(Math.floor(seconds)).padStart(2,"0")}`;
}
function clamp(value, min, max) { return Math.max(min, Math.min(max, value)); }
function status(text, error = false) {
  const el = $("status"); el.textContent = text; el.style.background = error ? "#8e3342" : "#2d2930"; el.classList.remove("hidden");
  clearTimeout(status.timer); status.timer = setTimeout(() => el.classList.add("hidden"), 5000);
}
function mergeCuts(items) {
  const sorted = items.map(x => ({start:clamp(x.start,0,duration), end:clamp(x.end,0,duration)}))
    .filter(x => x.end - x.start >= .05).sort((a,b) => a.start-b.start), merged=[];
  for (const item of sorted) { const last=merged.at(-1); if(last && item.start <= last.end+.001) last.end=Math.max(last.end,item.end); else merged.push(item); }
  return merged;
}
function cutAt(time) { return cuts.find(c => time >= c.start-.01 && time < c.end-.01); }
function windowEnd() { return viewportStart + WINDOW_SECONDS; }
function viewportBounds() { return {min:-WINDOW_SECONDS/2,max:Math.max(-WINDOW_SECONDS/2,duration-WINDOW_SECONDS/2)}; }
function followPlayhead() { const bounds=viewportBounds();viewportStart=clamp(audio.currentTime-WINDOW_SECONDS/2,bounds.min,bounds.max); }
function seek(value, follow = true) { audio.currentTime = clamp(value,0,duration); if(follow) followPlayhead(); render(); }

function resizeCanvas() {
  const rect=canvas.getBoundingClientRect(), ratio=window.devicePixelRatio||1;
  canvas.width=Math.max(1,Math.round(rect.width*ratio)); canvas.height=Math.max(1,Math.round(rect.height*ratio)); draw();
}
function draw() {
  if(!duration) return;
  const w=canvas.width,h=canvas.height,ratio=window.devicePixelRatio||1,style=getComputedStyle(document.documentElement), end=windowEnd(), span=WINDOW_SECONDS;
  ctx.clearRect(0,0,w,h); ctx.fillStyle=getComputedStyle(document.body).backgroundColor; ctx.fillRect(0,0,w,h);
  ctx.strokeStyle=style.getPropertyValue("--line"); ctx.lineWidth=ratio; ctx.fillStyle=style.getPropertyValue("--muted"); ctx.font=`${10*ratio}px sans-serif`;
  for(let second=Math.ceil(viewportStart/5)*5; second<=end; second+=5){const x=(second-viewportStart)/span*w;ctx.beginPath();ctx.moveTo(x,0);ctx.lineTo(x,h);ctx.stroke();ctx.fillText(formatTime(second,false),x+4*ratio,17*ratio)}
  const first=Math.max(0,Math.floor(viewportStart/duration*peaks.length)), last=Math.min(peaks.length-1,Math.ceil(end/duration*peaks.length));
  ctx.strokeStyle=style.getPropertyValue("--wave"); ctx.lineWidth=Math.max(1,ratio); ctx.beginPath(); const mid=h*.55;
  for(let i=first;i<=last;i++){const t=i/Math.max(1,peaks.length-1)*duration,x=(t-viewportStart)/span*w,amp=peaks[i]*h*.38;ctx.moveTo(x,mid-amp);ctx.lineTo(x,mid+amp)} ctx.stroke();
  for(const cut of cuts){const left=Math.max(cut.start,viewportStart),right=Math.min(cut.end,end);if(right>left){ctx.fillStyle=style.getPropertyValue("--cut");ctx.fillRect((left-viewportStart)/span*w,0,(right-left)/span*w,h)}}
  ctx.strokeStyle=style.getPropertyValue("--split");ctx.lineWidth=ratio;
  for(const point of splits){if(point<=viewportStart||point>=end)continue;const x=(point-viewportStart)/span*w;ctx.beginPath();ctx.moveTo(x,0);ctx.lineTo(x,h);ctx.stroke()}
  if(!audio.paused){followPlayhead(); requestAnimationFrame(draw);}
}
function render() {
  $("current").textContent=formatTime(audio.currentTime); $("window-start").textContent=formatTime(viewportStart,false); $("window-end").textContent=formatTime(windowEnd(),false);
  renderSegments(); draw();
}
async function buildWaveform(file) {
  const context=new(window.AudioContext||window.webkitAudioContext)();
  try {const buffer=await context.decodeAudioData(await file.arrayBuffer()),channel=buffer.getChannelData(0),bins=Math.min(6000,Math.max(1200,Math.floor(buffer.duration*16))),step=Math.max(1,Math.floor(channel.length/bins));peaks=[];for(let i=0;i<bins;i++){let max=0,start=i*step,end=Math.min(channel.length,start+step);for(let j=start;j<end;j++)max=Math.max(max,Math.abs(channel[j]));peaks.push(max)}duration=buffer.duration;} finally {await context.close();}
  resizeCanvas();
}
function segmentBounds(time=audio.currentTime) {
  const points=[0,...splits,duration].sort((a,b)=>a-b); let index=points.findIndex(p=>p>time)-1;
  if(index<0) index=Math.max(0,points.length-2); return {start:points[index],end:points[index+1],index};
}
function renderSegments() {
  const list=$("segment-list"); list.replaceChildren(); if(!duration)return; const points=[0,...splits,duration].sort((a,b)=>a-b), active=segmentBounds();
  for(let i=0;i<points.length-1;i++){const button=document.createElement("button"),deleted=cuts.some(c=>c.start<=points[i]+.01&&c.end>=points[i+1]-.01);button.type="button";button.className=`segment-chip${i===active.index?" active":""}${deleted?" deleted":""}`;button.textContent=`${i+1} · ${formatTime(points[i])}–${formatTime(points[i+1])}`;button.addEventListener("click",()=>seek((points[i]+points[i+1])/2));list.append(button)}
  $("delete-segment").disabled=active.end-active.start<.05; $("undo").disabled=!cuts.length;
}
async function loadFile(file) {
  if(!file)return; if(!/\.mp3$/i.test(file.name)){status("MP3 파일을 선택해주세요.",true);return}
  sourceFile=file;cuts=[];splits=[];peaks=[];duration=0;viewportStart=0;if(objectUrl)URL.revokeObjectURL(objectUrl);objectUrl=URL.createObjectURL(file);audio.src=objectUrl;
  $("filename").textContent=file.name;$("filemeta").textContent=`${(file.size/1024/1024).toFixed(1)}MB`;$("editor").classList.remove("hidden");$("loading").classList.remove("hidden");$("file").closest("label").classList.add("hidden");
  try{await new Promise((resolve,reject)=>{audio.onloadedmetadata=resolve;audio.onerror=reject});await buildWaveform(file);followPlayhead();$("duration").textContent=`전체 ${formatTime(duration)}`;$("filemeta").textContent+=` · ${formatTime(duration)}`;render()}catch(e){status("이 MP3의 파형을 분석하지 못했습니다.",true)}finally{$("loading").classList.add("hidden")}
}

canvas.addEventListener("pointerdown",e=>{drag={x:e.clientX,start:viewportStart,moved:false};canvas.setPointerCapture(e.pointerId)});
canvas.addEventListener("pointermove",e=>{if(!drag)return;const dx=e.clientX-drag.x;if(Math.abs(dx)>3)drag.moved=true;const bounds=viewportBounds();viewportStart=clamp(drag.start-dx/canvas.clientWidth*WINDOW_SECONDS,bounds.min,bounds.max);audio.currentTime=clamp(viewportStart+WINDOW_SECONDS/2,0,duration);render()});
canvas.addEventListener("pointerup",e=>{if(!drag)return;if(!drag.moved){const rect=canvas.getBoundingClientRect();seek(viewportStart+(e.clientX-rect.left)/rect.width*WINDOW_SECONDS)}drag=null});
$("file").addEventListener("change",e=>loadFile(e.target.files[0])); $("replace").addEventListener("click",()=>$("file").click());
$("play").addEventListener("click",async()=>{if(audio.paused){const cut=cutAt(audio.currentTime);if(cut)seek(cut.end);await audio.play();$("play").textContent="Ⅱ";draw()}else audio.pause()});
$("back").addEventListener("click",()=>seek(audio.currentTime-5)); $("forward").addEventListener("click",()=>seek(audio.currentTime+5));
audio.addEventListener("timeupdate",()=>{const cut=cutAt(audio.currentTime);if(cut)audio.currentTime=cut.end;followPlayhead();$("current").textContent=formatTime(audio.currentTime);$("window-start").textContent=formatTime(viewportStart,false);$("window-end").textContent=formatTime(windowEnd(),false);renderSegments()});
audio.addEventListener("ended",()=>{$("play").textContent="▶";render()}); audio.addEventListener("pause",()=>{$("play").textContent="▶";render()});
$("split").addEventListener("click",()=>{const point=audio.currentTime;if(point<.05||duration-point<.05)return;if(!splits.some(x=>Math.abs(x-point)<.05)){splits.push(point);splits.sort((a,b)=>a-b);status(`${formatTime(point)}에서 분할했습니다.`);render()}});
$("delete-segment").addEventListener("click",()=>{const segment=segmentBounds();cuts=mergeCuts([...cuts,segment]);status(`${formatTime(segment.start)}–${formatTime(segment.end)} 조각을 삭제 대상으로 표시했습니다.`);render()});
$("undo").addEventListener("click",()=>{cuts.pop();render()});
$("export").addEventListener("click",async()=>{if(!sourceFile)return;const button=$("export"),form=new FormData();form.append("file",sourceFile,sourceFile.name);form.append("cuts",JSON.stringify(cuts));button.disabled=true;button.textContent="처리 중";status("삭제한 조각을 제외하고 MP3를 만드는 중입니다…");try{const response=await fetch("/api/audio-editor/export",{method:"POST",credentials:"same-origin",body:form});if(!response.ok){const data=await response.json().catch(()=>({}));throw new Error(data.detail||"내보내지 못했습니다")}const blob=await response.blob(),url=URL.createObjectURL(blob),link=document.createElement("a");link.href=url;link.download=`${sourceFile.name.replace(/\.mp3$/i,"")}-편집본.mp3`;document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),30000);status("편집한 MP3 다운로드를 시작했습니다.")}catch(e){status(e.message,true)}finally{button.disabled=false;button.textContent="내보내기"}});
window.addEventListener("resize",resizeCanvas); window.matchMedia("(prefers-color-scheme: dark)").addEventListener?.("change",draw);
